class DSBX_QA_Ext : Managed
{
	DSBX_QA_Probe m_Probe;
	DSBX_QA_JobMgr m_Jobs;

	void Init(DSBX_QA_Probe probe)
	{
		m_Probe = probe;
		if (probe)
		{
			m_Jobs = probe.m_Jobs;
		}
	}

	bool Handles(string verb, string role)
	{
		return false;
	}

	void OnStartOp(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		res.status = "rejected";
		res.reason = "unknown_verb";
	}

	void OnTick(float timeslice)
	{
	}

	void OnJobEnd(string job_id, string state, string reason)
	{
	}

	void OnRpc(PlayerIdentity sender, Object target, int rpc_type, ParamsReadContext ctx)
	{
	}

	void OnShutdown()
	{
	}
}

class DSBX_QA_Job : Managed
{
	string m_JobId;
	DSBX_QA_Ext m_Owner;
	string m_Resource;
	string m_State;
	string m_Reason;
	string m_Deadman;
	ref array<string> m_Ncol;
	ref array<string> m_Scol;
	ref array<float> m_Ncell;
	ref array<string> m_Scell;
	int m_RowsTotal;
	int m_PageSize;
	int m_MaxRows;
	float m_MaxDurationMs;
	float m_StartTickMs;
	float m_EndTickMs;
	float m_OnJobEndTickMs;
	float m_ReleasedTickMs;
	float m_ElapsedDtsumMs;
	bool m_EndDeferred;
	bool m_Released;
	bool m_FreezeOnWait;
	bool m_DeferCleanup;
	bool m_ExtHandlesDeadman;

	void DSBX_QA_Job()
	{
		m_JobId = "";
		m_Owner = null;
		m_Resource = "";
		m_State = "";
		m_Reason = "";
		m_Deadman = "";
		m_Ncol = new array<string>();
		m_Scol = new array<string>();
		m_Ncell = new array<float>();
		m_Scell = new array<string>();
		m_RowsTotal = 0;
		m_PageSize = 20;
		m_MaxRows = 4096;
		m_MaxDurationMs = 900000.0;
		m_StartTickMs = 0.0;
		m_EndTickMs = 0.0;
		m_OnJobEndTickMs = 0.0;
		m_ReleasedTickMs = 0.0;
		m_ElapsedDtsumMs = 0.0;
		m_EndDeferred = false;
		m_Released = false;
		m_FreezeOnWait = false;
		m_DeferCleanup = false;
		m_ExtHandlesDeadman = false;
	}
}

class DSBX_QA_JobMgr : Managed
{
	const int JOB_MAX_LIVE = 8;
	const int JOB_MAX_ROWS = 4096;
	const float JOB_MAX_DURATION_MS = 900000.0;
	const int JOB_MAX_RETAINED = 16;

	DSBX_QA_Probe m_Probe;
	ref array<ref DSBX_QA_Job> m_Live;
	ref array<ref DSBX_QA_Job> m_Retained;
	ref array<string> m_ScratchIds;

	void DSBX_QA_JobMgr(DSBX_QA_Probe probe)
	{
		m_Probe = probe;
		m_Live = new array<ref DSBX_QA_Job>();
		m_Retained = new array<ref DSBX_QA_Job>();
		m_ScratchIds = new array<string>();
	}

	float NowMs()
	{
		if (m_Probe)
		{
			return m_Probe.NowMs();
		}
		return 0.0;
	}

	int LiveCount()
	{
		int n = 0;
		int i = 0;
		while (i < m_Live.Count())
		{
			DSBX_QA_Job job = m_Live.Get(i);
			if (job && job.m_State == "running")
			{
				n = n + 1;
			}
			i = i + 1;
		}
		return n;
	}

	DSBX_QA_Job FindLive(string job_id)
	{
		int i = 0;
		while (i < m_Live.Count())
		{
			DSBX_QA_Job job = m_Live.Get(i);
			if (job && job.m_JobId == job_id)
			{
				return job;
			}
			i = i + 1;
		}
		return null;
	}

	DSBX_QA_Job GetJob(string job_id)
	{
		DSBX_QA_Job live = FindLive(job_id);
		if (live)
		{
			return live;
		}
		int i = 0;
		while (i < m_Retained.Count())
		{
			DSBX_QA_Job kept = m_Retained.Get(i);
			if (kept && kept.m_JobId == job_id)
			{
				return kept;
			}
			i = i + 1;
		}
		return null;
	}

	string StartJob(DSBX_QA_Ext owner, string job_id, string resource, array<string> ncol, array<string> scol, int page_size, int max_rows, float max_duration_ms, string deadman)
	{
		// Mismo orden de validación que start_job de qa/fake_peer.py.
		if (deadman != "stop" && deadman != "continue")
		{
			return "bad_deadman";
		}
		if (resource == "")
		{
			return "bad_args";
		}
		if (job_id == "" || GetJob(job_id))
		{
			return "bad_args";
		}
		if (page_size <= 0 || max_rows <= 0 || max_duration_ms <= 0.0)
		{
			return "bad_args";
		}
		if (max_rows > JOB_MAX_ROWS)
		{
			max_rows = JOB_MAX_ROWS;
		}
		if (max_duration_ms > JOB_MAX_DURATION_MS)
		{
			max_duration_ms = JOB_MAX_DURATION_MS;
		}
		int liveN = 0;
		int i = 0;
		while (i < m_Live.Count())
		{
			DSBX_QA_Job other = m_Live.Get(i);
			if (other && !other.m_Released)
			{
				if (other.m_Resource == resource)
				{
					return "busy";
				}
			}
			if (other && other.m_State == "running")
			{
				liveN = liveN + 1;
			}
			i = i + 1;
		}
		if (liveN >= JOB_MAX_LIVE)
		{
			return "too_many_jobs";
		}
		DSBX_QA_Job job = new DSBX_QA_Job();
		job.m_JobId = job_id;
		job.m_Owner = owner;
		job.m_Resource = resource;
		job.m_State = "running";
		job.m_Reason = "";
		job.m_Deadman = deadman;
		job.m_PageSize = page_size;
		job.m_MaxRows = max_rows;
		job.m_MaxDurationMs = max_duration_ms;
		job.m_StartTickMs = NowMs();
		if (ncol)
		{
			int ci = 0;
			while (ci < ncol.Count())
			{
				job.m_Ncol.Insert(ncol.Get(ci));
				ci = ci + 1;
			}
		}
		if (scol)
		{
			int si = 0;
			while (si < scol.Count())
			{
				job.m_Scol.Insert(scol.Get(si));
				si = si + 1;
			}
		}
		m_Live.Insert(job);
		return "";
	}

	void FillStartRead(DSBX_QA_Read read, string job_id, string resource)
	{
		read.has.Insert("payload");
		read.sk.Insert("job");
		read.sk.Insert("state");
		read.sk.Insert("resource");
		read.sv.Insert(job_id);
		read.sv.Insert("running");
		read.sv.Insert(resource);
	}

	bool AppendRow(string job_id, array<float> nvals, array<string> svals)
	{
		DSBX_QA_Job job = FindLive(job_id);
		if (!job)
		{
			return false;
		}
		if (job.m_State != "running")
		{
			return false;
		}
		if (!nvals || !svals)
		{
			return false;
		}
		if (nvals.Count() != job.m_Ncol.Count())
		{
			return false;
		}
		if (svals.Count() != job.m_Scol.Count())
		{
			return false;
		}
		if (job.m_RowsTotal + 1 > job.m_MaxRows)
		{
			EndJob(job_id, "failed", "rows_cap");
			return false;
		}
		int i = 0;
		while (i < nvals.Count())
		{
			job.m_Ncell.Insert(nvals.Get(i));
			i = i + 1;
		}
		int j = 0;
		while (j < svals.Count())
		{
			job.m_Scell.Insert(svals.Get(j));
			j = j + 1;
		}
		job.m_RowsTotal = job.m_RowsTotal + 1;
		return true;
	}

	string GetState(string job_id)
	{
		DSBX_QA_Job job = GetJob(job_id);
		if (!job)
		{
			return "";
		}
		return job.m_State;
	}

	void MoveToRetained(DSBX_QA_Job job)
	{
		int i = 0;
		while (i < m_Live.Count())
		{
			if (m_Live.Get(i) == job)
			{
				m_Live.RemoveOrdered(i);
				break;
			}
			i = i + 1;
		}
		m_Retained.Insert(job);
		while (m_Retained.Count() > JOB_MAX_RETAINED)
		{
			m_Retained.RemoveOrdered(0);
		}
	}

	bool ExpireAsTimeout(string job_id)
	{
		// Mismo estado y motivo que la expiración por max_duration_ms de TickJobs; los motivos del gestor viven aquí
		// y no en las extensiones (regla estática 10). Lo usa el mutante early_end de X_Base.
		return EndJob(job_id, "expired", "job_timeout");
	}

	bool IsDeadmanTripped(string job_id)
	{
		// Igual que JobMgr.is_deadman_tripped: solo un trabajo "stop" en marcha con el lease del peer caducado.
		DSBX_QA_Job job = FindLive(job_id);
		if (!job || job.m_State != "running" || job.m_Deadman != "stop")
		{
			return false;
		}
		if (!m_Probe)
		{
			return false;
		}
		return !m_Probe.LeaseOk();
	}

	void FinalizeCleanup(DSBX_QA_Job job)
	{
		if (job.m_Owner)
		{
			job.m_Owner.OnJobEnd(job.m_JobId, job.m_State, job.m_Reason);
		}
		job.m_OnJobEndTickMs = NowMs();
		job.m_Released = true;
		job.m_ReleasedTickMs = NowMs();
		MoveToRetained(job);
	}

	bool EndJob(string job_id, string state, string reason)
	{
		// Única transición terminal (§3.1): fija state, reason y end_tick_ms una sola vez.
		if (state != "done" && state != "stopped" && state != "failed" && state != "expired")
		{
			return false;
		}
		DSBX_QA_Job job = FindLive(job_id);
		if (!job)
		{
			return false;
		}
		if (job.m_State != "running")
		{
			return false;
		}
		job.m_State = state;
		job.m_Reason = reason;
		job.m_EndTickMs = NowMs();
		// Mutante defer_cleanup (N4): sin transporte, OnJobEnd y la liberación esperan al primer poll 200.
		if (job.m_DeferCleanup && reason != "shutdown" && m_Probe && m_Probe.IsTransportWaiting())
		{
			job.m_EndDeferred = true;
			return true;
		}
		FinalizeCleanup(job);
		return true;
	}

	void CompleteDeferredEnds()
	{
		m_ScratchIds.Clear();
		int i = 0;
		while (i < m_Live.Count())
		{
			DSBX_QA_Job job = m_Live.Get(i);
			if (job && job.m_EndDeferred)
			{
				m_ScratchIds.Insert(job.m_JobId);
			}
			i = i + 1;
		}
		int k = 0;
		while (k < m_ScratchIds.Count())
		{
			string jobId = m_ScratchIds.Get(k);
			DSBX_QA_Job kept = FindLive(jobId);
			if (kept && kept.m_EndDeferred)
			{
				kept.m_EndDeferred = false;
				FinalizeCleanup(kept);
			}
			k = k + 1;
		}
		m_ScratchIds.Clear();
	}

	bool FreeJob(string job_id)
	{
		int i = 0;
		while (i < m_Retained.Count())
		{
			DSBX_QA_Job job = m_Retained.Get(i);
			if (job && job.m_JobId == job_id)
			{
				m_Retained.RemoveOrdered(i);
				return true;
			}
			i = i + 1;
		}
		return false;
	}

	void TickJobs(float timeslice, float now_ms)
	{
		m_ScratchIds.Clear();
		int i = 0;
		while (i < m_Live.Count())
		{
			DSBX_QA_Job job = m_Live.Get(i);
			if (job)
			{
				m_ScratchIds.Insert(job.m_JobId);
			}
			i = i + 1;
		}
		int k = 0;
		while (k < m_ScratchIds.Count())
		{
			string jobId = m_ScratchIds.Get(k);
			DSBX_QA_Job live = FindLive(jobId);
			if (live && live.m_State == "running")
			{
				bool frozen = false;
				if (live.m_FreezeOnWait && m_Probe && m_Probe.IsTransportWaiting())
				{
					frozen = true;
				}
				if (!frozen)
				{
					live.m_ElapsedDtsumMs = live.m_ElapsedDtsumMs + timeslice * 1000.0;
					// F02-H3 (§14.0): un trabajo "stop" sin lease vigente termina en failed/lease_expired por la
					// transición única, como tick_jobs de qa/fake_peer.py. Un dueño que necesita registrar su propia
					// fila antes (el efecto de BASE-11, blocked_lease) lo declara con m_ExtHandlesDeadman (H3 de Sol r1).
					if (live.m_Deadman == "stop" && !live.m_ExtHandlesDeadman && m_Probe && !m_Probe.LeaseOk())
					{
						EndJob(jobId, "failed", "lease_expired");
					}
					else if (now_ms - live.m_StartTickMs > live.m_MaxDurationMs)
					{
						EndJob(jobId, "expired", "job_timeout");
					}
				}
			}
			k = k + 1;
		}
		m_ScratchIds.Clear();
	}

	void ShutdownJobs()
	{
		m_ScratchIds.Clear();
		int i = 0;
		while (i < m_Live.Count())
		{
			DSBX_QA_Job job = m_Live.Get(i);
			if (job && job.m_State == "running")
			{
				m_ScratchIds.Insert(job.m_JobId);
			}
			i = i + 1;
		}
		int k = 0;
		while (k < m_ScratchIds.Count())
		{
			EndJob(m_ScratchIds.Get(k), "stopped", "shutdown");
			k = k + 1;
		}
		m_ScratchIds.Clear();
		CompleteDeferredEnds();
	}
}
