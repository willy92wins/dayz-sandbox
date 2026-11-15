const int DSBX_QA_RPC_BASE_PING = 26102880;

class DSBX_QA_PingEntry : Managed
{
	int m_Token;
	float m_RecvMs;

	void DSBX_QA_PingEntry()
	{
		m_Token = 0;
		m_RecvMs = 0.0;
	}
}

// Un trabajo temporizador en marcha (el A de qa_timer_start o el testigo B). Misma semántica que
// active_timers de qa/fake_ext_base.py: como mucho una muestra por tick, con el dtsum_ms real.
class DSBX_QA_TimerRun : Managed
{
	bool m_Active;
	string m_JobId;
	float m_DurationMs;
	float m_StepMs;
	float m_DtsumMs;
	float m_NextMs;
	int m_Seq;
	bool m_Freeze;

	void DSBX_QA_TimerRun()
	{
		m_Active = false;
		m_JobId = "";
		m_DurationMs = 0.0;
		m_StepMs = 0.0;
		m_DtsumMs = 0.0;
		m_NextMs = 0.0;
		m_Seq = 0;
		m_Freeze = false;
	}

	void Begin(string jobId, float durationMs, float stepMs, bool freeze)
	{
		m_Active = true;
		m_JobId = jobId;
		m_DurationMs = durationMs;
		m_StepMs = stepMs;
		m_DtsumMs = 0.0;
		m_NextMs = 0.0;
		m_Seq = 0;
		m_Freeze = freeze;
	}
}

class DSBX_QA_X_Base : DSBX_QA_Ext
{
	bool m_InitDone;
	int m_TicksN;
	int m_EndCallsN;
	string m_LastEndJob;
	string m_LastEndState;
	string m_LastEndReason;
	int m_RpcPingCount;
	int m_RpcLastToken;
	ref array<ref DSBX_QA_PingEntry> m_PingLog;
	ref DSBX_QA_TimerRun m_TimerRun;
	ref DSBX_QA_TimerRun m_WitnessRun;
	bool m_WitnessArmed;
	string m_WitnessJobId;
	string m_WitnessResource;
	float m_WitnessStartedTickMs;
	int m_WitnessAttemptsN;
	ref array<string> m_TimerNcol;
	ref array<string> m_EffectNcol;
	ref array<string> m_EffectScol;
	ref array<string> m_NoScol;
	bool m_EffectActive;
	string m_EffectJobId;
	float m_EffectPeriodMs;
	int m_EffectCount;
	int m_EffectToken0;
	string m_EffectClientInst;
	float m_EffectDtsumMs;
	float m_EffectNextMs;
	int m_EffectSent;
	bool m_EffectIgnore;
	bool m_EffectSkip;

	void DSBX_QA_X_Base()
	{
		m_InitDone = false;
		m_TicksN = 0;
		m_EndCallsN = 0;
		m_LastEndJob = "";
		m_LastEndState = "";
		m_LastEndReason = "";
		m_RpcPingCount = 0;
		m_RpcLastToken = 0;
		m_PingLog = new array<ref DSBX_QA_PingEntry>();
		m_TimerRun = new DSBX_QA_TimerRun();
		m_WitnessRun = new DSBX_QA_TimerRun();
		m_WitnessArmed = false;
		m_WitnessJobId = "";
		m_WitnessResource = "";
		m_WitnessStartedTickMs = 0.0;
		m_WitnessAttemptsN = 0;
		m_TimerNcol = new array<string>();
		m_TimerNcol.Insert("seq_n");
		m_TimerNcol.Insert("frame");
		m_TimerNcol.Insert("tick_ms");
		m_TimerNcol.Insert("dtsum_ms");
		m_EffectNcol = new array<string>();
		m_EffectNcol.Insert("token_n");
		m_EffectNcol.Insert("tick_ms");
		m_EffectNcol.Insert("lease_age_ms");
		m_EffectScol = new array<string>();
		m_EffectScol.Insert("outcome");
		m_NoScol = new array<string>();
		m_EffectActive = false;
		m_EffectJobId = "";
		m_EffectPeriodMs = 0.0;
		m_EffectCount = 0;
		m_EffectToken0 = 0;
		m_EffectClientInst = "";
		m_EffectDtsumMs = 0.0;
		m_EffectNextMs = 0.0;
		m_EffectSent = 0;
		m_EffectIgnore = false;
		m_EffectSkip = false;
	}

	override void Init(DSBX_QA_Probe probe)
	{
		super.Init(probe);
		m_InitDone = true;
	}

	override bool Handles(string verb, string role)
	{
		if (verb == "qa_echo" || verb == "qa_timer_start" || verb == "qa_info" || verb == "qa_cache_fill" || verb == "qa_cache_snapshot" || verb == "qa_cache_page")
		{
			return true;
		}
		if (role == "server" && (verb == "qa_rpc_ping" || verb == "qa_effect_start" || verb == "qa_emitlog_page"))
		{
			return true;
		}
		if (role == "client" && (verb == "qa_rpclog_page" || verb == "qa_ping_page"))
		{
			return true;
		}
		return false;
	}

	bool GetStr(DSBX_QA_Args args, string key, out string value)
	{
		value = "";
		int i = 0;
		while (i < args.sk.Count())
		{
			if (args.sk.Get(i) == key)
			{
				value = args.sv.Get(i);
				return true;
			}
			i = i + 1;
		}
		return false;
	}

	bool GetNum(DSBX_QA_Args args, string key, out float value)
	{
		value = 0.0;
		int i = 0;
		while (i < args.nk.Count())
		{
			if (args.nk.Get(i) == key)
			{
				value = args.nv.Get(i);
				return true;
			}
			i = i + 1;
		}
		return false;
	}

	void Reject(DSBX_QA_Result res, string reason)
	{
		res.status = "rejected";
		res.reason = reason;
	}

	bool IsHex16(string value)
	{
		if (value.Length() != 16)
		{
			return false;
		}
		string allowed = "0123456789abcdef";
		int i = 0;
		while (i < value.Length())
		{
			if (allowed.IndexOf(value.Substring(i, 1)) < 0)
			{
				return false;
			}
			i = i + 1;
		}
		return true;
	}

	bool SendPing(int token, string clientInst)
	{
		ScriptRPC rpc = new ScriptRPC();
		if (!rpc.Write(token))
		{
			return false;
		}
		if (!rpc.Write(clientInst))
		{
			return false;
		}
		rpc.Send(null, DSBX_QA_RPC_BASE_PING, true, null);
		return true;
	}

	override void OnStartOp(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string verb = op.verb;
		if (verb == "qa_echo")
		{
			DoEcho(op, args, res);
			return;
		}
		if (verb == "qa_timer_start")
		{
			DoTimerStart(op, args, res);
			return;
		}
		if (verb == "qa_rpc_ping")
		{
			DoRpcPing(op, args, res);
			return;
		}
		if (verb == "qa_info")
		{
			DoInfo(op, args, res);
			return;
		}
		if (verb == "qa_cache_fill")
		{
			DoCacheFill(op, args, res);
			return;
		}
		if (verb == "qa_cache_snapshot")
		{
			DoCacheSnapshot(op, args, res);
			return;
		}
		if (verb == "qa_cache_page")
		{
			DoCachePage(op, args, res);
			return;
		}
		if (verb == "qa_rpclog_page")
		{
			DoRpcLogPage(op, args, res);
			return;
		}
		if (verb == "qa_ping_page")
		{
			DoPingPage(op, args, res);
			return;
		}
		if (verb == "qa_emitlog_page")
		{
			DoEmitLogPage(op, args, res);
			return;
		}
		if (verb == "qa_effect_start")
		{
			DoEffectStart(op, args, res);
			return;
		}
		Reject(res, "unknown_verb");
	}

	void DoEcho(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		float padF;
		int padN = 0;
		if (GetNum(args, "pad_bytes_n", padF))
		{
			if (!m_Probe.IsIntF(padF) || padF < 0.0)
			{
				Reject(res, "bad_args");
				return;
			}
			padN = (int)padF;
		}
		float svChars = 0.0;
		int i = 0;
		while (i < args.sv.Count())
		{
			svChars = svChars + args.sv.Get(i).Length();
			i = i + 1;
		}
		int j = 0;
		while (j < args.scell.Count())
		{
			svChars = svChars + args.scell.Get(j).Length();
			j = j + 1;
		}
		float numSum = 0.0;
		int a = 0;
		while (a < args.nv.Count())
		{
			numSum = numSum + args.nv.Get(a);
			a = a + 1;
		}
		int b = 0;
		while (b < args.ncell.Count())
		{
			numSum = numSum + args.ncell.Get(b);
			b = b + 1;
		}
		string firstSk = "";
		if (args.sk.Count() > 0)
		{
			firstSk = args.sk.Get(0);
		}
		string lastSv = "";
		if (args.sv.Count() > 0)
		{
			lastSv = args.sv.Get(args.sv.Count() - 1);
		}
		string pad = "";
		while (pad.Length() + 8 <= padN)
		{
			pad = pad + "xxxxxxxx";
		}
		while (pad.Length() < padN)
		{
			pad = pad + "x";
		}
		float initB = 0.0;
		if (m_InitDone)
		{
			initB = 1.0;
		}
		res.read.has.Insert("payload");
		res.read.nk.Insert("sk_n");
		res.read.nk.Insert("nk_n");
		res.read.nk.Insert("rows_n");
		res.read.nk.Insert("ncol_n");
		res.read.nk.Insert("scol_n");
		res.read.nk.Insert("sv_chars_n");
		res.read.nk.Insert("num_sum");
		res.read.nk.Insert("tick_ms");
		res.read.nk.Insert("frame");
		res.read.nk.Insert("ext_init_b");
		res.read.nk.Insert("ext_ticks_n");
		res.read.nk.Insert("ext_end_calls_n");
		res.read.nk.Insert("witness_started_tick_ms");
		res.read.nk.Insert("witness_attempts_n");
		res.read.nk.Insert("rpc_ping_count_n");
		res.read.nk.Insert("rpc_last_token_n");
		res.read.nv.Insert(args.sk.Count());
		res.read.nv.Insert(args.nk.Count());
		res.read.nv.Insert(args.rows);
		res.read.nv.Insert(args.ncol.Count());
		res.read.nv.Insert(args.scol.Count());
		res.read.nv.Insert(svChars);
		res.read.nv.Insert(numSum);
		res.read.nv.Insert(m_Probe.NowMs());
		res.read.nv.Insert(m_Probe.m_Frame);
		res.read.nv.Insert(initB);
		res.read.nv.Insert(m_TicksN);
		res.read.nv.Insert(m_EndCallsN);
		res.read.nv.Insert(m_WitnessStartedTickMs);
		res.read.nv.Insert(m_WitnessAttemptsN);
		res.read.nv.Insert(m_RpcPingCount);
		res.read.nv.Insert(m_RpcLastToken);
		res.read.sk.Insert("first_sk");
		res.read.sk.Insert("last_sv");
		res.read.sk.Insert("ext_last_end_job");
		res.read.sk.Insert("ext_last_end_state");
		res.read.sk.Insert("ext_last_end_reason");
		res.read.sk.Insert("witness_job_id");
		res.read.sk.Insert("pad");
		res.read.sv.Insert(firstSk);
		res.read.sv.Insert(lastSv);
		res.read.sv.Insert(m_LastEndJob);
		res.read.sv.Insert(m_LastEndState);
		res.read.sv.Insert(m_LastEndReason);
		res.read.sv.Insert(m_WitnessJobId);
		res.read.sv.Insert(pad);
	}

	void DoTimerStart(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		float durationF;
		float stepF;
		if (!GetNum(args, "duration_ms", durationF) || !GetNum(args, "sample_step_ms", stepF))
		{
			Reject(res, "bad_args");
			return;
		}
		if (!m_Probe.IsFiniteF(durationF) || !m_Probe.IsFiniteF(stepF) || durationF <= 0.0 || stepF < 0.0)
		{
			Reject(res, "bad_args");
			return;
		}
		int maxRows = 4096;
		float maxDur = 900000.0;
		float optF;
		if (GetNum(args, "max_rows_n", optF))
		{
			if (!m_Probe.IsIntF(optF) || optF <= 0.0)
			{
				Reject(res, "bad_args");
				return;
			}
			maxRows = (int)optF;
		}
		if (GetNum(args, "max_duration_ms", optF))
		{
			if (!m_Probe.IsFiniteF(optF) || optF <= 0.0)
			{
				Reject(res, "bad_args");
				return;
			}
			maxDur = optF;
		}
		float witnessF = 0.0;
		bool hasWitness = GetNum(args, "witness_b", witnessF);
		if (hasWitness && witnessF != 0.0 && witnessF != 1.0)
		{
			Reject(res, "bad_args");
			return;
		}
		string err = m_Jobs.StartJob(this, op.op_id, "qa_timer", m_TimerNcol, m_NoScol, 20, maxRows, maxDur, "continue");
		if (err != "")
		{
			Reject(res, err);
			return;
		}
		string fault = m_Probe.GetOpFault();
		bool freezeWait = fault == "freeze_on_wait";
		bool deferClean = fault == "defer_cleanup";
		DSBX_QA_Job job = m_Jobs.GetJob(op.op_id);
		if (job)
		{
			job.m_FreezeOnWait = freezeWait;
			job.m_DeferCleanup = deferClean;
		}
		m_TimerRun.Begin(op.op_id, durationF, stepF, freezeWait);
		if (hasWitness && witnessF == 1.0)
		{
			ArmWitness(op.op_id, "qa_timer");
		}
		m_Jobs.FillStartRead(res.read, op.op_id, "qa_timer");
	}

	void ArmWitness(string opId, string resource)
	{
		m_WitnessArmed = true;
		m_WitnessResource = resource;
		m_WitnessJobId = opId + ":witness";
		m_WitnessStartedTickMs = 0.0;
		m_WitnessAttemptsN = 0;
	}

	void DoRpcPing(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		float tokenF;
		string clientInst;
		if (!GetNum(args, "token_n", tokenF) || !GetStr(args, "client_inst", clientInst))
		{
			Reject(res, "bad_args");
			return;
		}
		if (!m_Probe.IsIntF(tokenF) || tokenF <= 0.0 || clientInst == "")
		{
			Reject(res, "bad_args");
			return;
		}
		if (!m_Probe.LeaseOk())
		{
			res.status = "error";
			res.reason = "lease_expired";
			return;
		}
		if (!SendPing((int)tokenF, clientInst))
		{
			res.status = "error";
			res.reason = "rpc_write_failed";
			return;
		}
		res.read.has.Insert("payload");
		res.read.nk.Insert("sent_token_n");
		res.read.nv.Insert(tokenF);
	}

	void DoInfo(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		res.read.has.Insert("payload");
		res.read.sk.Insert("probe_ver");
		res.read.sk.Insert("role");
		res.read.sv.Insert("dsbx-qa1+" + DSBX_QA_STAMP);
		res.read.sv.Insert(m_Probe.GetRole());
		res.read.nk.Insert("callbacks_created_n");
		res.read.nk.Insert("callbacks_pooled_n");
		res.read.nk.Insert("callbacks_inflight_n");
		res.read.nk.Insert("callback_budget_n");
		res.read.nk.Insert("cache_size_n");
		res.read.nk.Insert("rpclog_size_n");
		res.read.nk.Insert("jobs_live_n");
		res.read.nv.Insert(m_Probe.CallbacksCreatedN());
		res.read.nv.Insert(m_Probe.CallbacksPooledN());
		res.read.nv.Insert(m_Probe.CallbacksInflightN());
		res.read.nv.Insert(m_Probe.CallbackBudgetN());
		res.read.nv.Insert(m_Probe.CacheSizeN());
		res.read.nv.Insert(m_Probe.RpcLogSizeN());
		res.read.nv.Insert(m_Probe.JobsLiveN());
	}

	void DoCacheFill(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		float nF;
		string fillId;
		if (!GetNum(args, "n_n", nF) || !GetStr(args, "fill_id", fillId))
		{
			Reject(res, "bad_args");
			return;
		}
		if (!m_Probe.IsIntF(nF) || nF < 1.0 || nF > 2048.0 || !IsHex16(fillId))
		{
			Reject(res, "bad_args");
			return;
		}
		int n = (int)nF;
		m_Probe.QaCacheFill(n, fillId);
		res.read.has.Insert("payload");
		res.read.nk.Insert("inserted_n");
		res.read.nk.Insert("cache_size_n");
		res.read.nv.Insert(n);
		res.read.nv.Insert(m_Probe.CacheSizeN());
		res.read.sk.Insert("first_id");
		res.read.sk.Insert("last_id");
		res.read.sv.Insert(fillId + "-0");
		res.read.sv.Insert(fillId + "-" + (n - 1));
	}

	void DoCacheSnapshot(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		int total = m_Probe.QaCacheSnapshot(op.op_id);
		res.read.has.Insert("payload");
		res.read.sk.Insert("snap_id");
		res.read.sv.Insert(op.op_id);
		res.read.nk.Insert("rows_total_n");
		res.read.nv.Insert(total);
	}

	bool PageRange(int total, int pageSize, int pageN, out int pagesN, out int startRow, out int endRow)
	{
		pagesN = 0;
		startRow = 0;
		endRow = 0;
		if (total > 0)
		{
			pagesN = (total + pageSize - 1) / pageSize;
		}
		if (pageN < 0 || (total == 0 && pageN > 0) || (total > 0 && pageN >= pagesN))
		{
			return false;
		}
		startRow = pageN * pageSize;
		endRow = startRow + pageSize;
		if (endRow > total)
		{
			endRow = total;
		}
		return true;
	}

	void DoCachePage(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string snapId;
		float pageF;
		if (!GetStr(args, "snap_id", snapId) || !GetNum(args, "page_n", pageF) || !m_Probe.IsIntF(pageF))
		{
			Reject(res, "bad_args");
			return;
		}
		if (snapId != m_Probe.CacheSnapId())
		{
			Reject(res, "bad_args");
			return;
		}
		int total = m_Probe.CacheSnapCount();
		int pagesN;
		int startRow;
		int endRow;
		if (!PageRange(total, 50, (int)pageF, pagesN, startRow, endRow))
		{
			Reject(res, "bad_args");
			return;
		}
		res.read.has.Insert("payload");
		res.read.nk.Insert("page_n");
		res.read.nk.Insert("pages_n");
		res.read.nk.Insert("rows_total_n");
		res.read.nv.Insert(pageF);
		res.read.nv.Insert(pagesN);
		res.read.nv.Insert(total);
		res.read.ncol.Insert("idx_n");
		res.read.scol.Insert("op_id");
		res.read.rows = endRow - startRow;
		int i = startRow;
		while (i < endRow)
		{
			res.read.ncell.Insert(i);
			res.read.scell.Insert(m_Probe.CacheSnapOpId(i));
			i = i + 1;
		}
	}

	void DoRpcLogPage(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		float pageF;
		if (!GetNum(args, "page_n", pageF) || !m_Probe.IsIntF(pageF))
		{
			Reject(res, "bad_args");
			return;
		}
		int total = m_Probe.RpcLogSizeN();
		int pagesN;
		int startRow;
		int endRow;
		if (!PageRange(total, 40, (int)pageF, pagesN, startRow, endRow))
		{
			Reject(res, "bad_args");
			return;
		}
		res.read.has.Insert("payload");
		res.read.nk.Insert("page_n");
		res.read.nk.Insert("pages_n");
		res.read.nk.Insert("rows_total_n");
		res.read.nv.Insert(pageF);
		res.read.nv.Insert(pagesN);
		res.read.nv.Insert(total);
		res.read.ncol.Insert("seq_n");
		res.read.ncol.Insert("recv_ms");
		res.read.ncol.Insert("lease_age_ms");
		res.read.ncol.Insert("idx_n");
		res.read.scol.Insert("decision");
		res.read.rows = endRow - startRow;
		int i = startRow;
		while (i < endRow)
		{
			DSBX_QA_RpcEntry entry = m_Probe.RpcLogEntry(i);
			res.read.ncell.Insert(entry.seq);
			res.read.ncell.Insert(entry.recv_ms);
			res.read.ncell.Insert(entry.lease_age_ms);
			res.read.ncell.Insert(i);
			res.read.scell.Insert(entry.decision);
			i = i + 1;
		}
	}

	void DoPingPage(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		float pageF;
		if (!GetNum(args, "page_n", pageF) || !m_Probe.IsIntF(pageF))
		{
			Reject(res, "bad_args");
			return;
		}
		int total = m_PingLog.Count();
		int pagesN;
		int startRow;
		int endRow;
		if (!PageRange(total, 40, (int)pageF, pagesN, startRow, endRow))
		{
			Reject(res, "bad_args");
			return;
		}
		res.read.has.Insert("payload");
		res.read.nk.Insert("page_n");
		res.read.nk.Insert("pages_n");
		res.read.nk.Insert("rows_total_n");
		res.read.nv.Insert(pageF);
		res.read.nv.Insert(pagesN);
		res.read.nv.Insert(total);
		res.read.ncol.Insert("token_n");
		res.read.ncol.Insert("recv_ms");
		res.read.ncol.Insert("idx_n");
		res.read.rows = endRow - startRow;
		int i = startRow;
		while (i < endRow)
		{
			DSBX_QA_PingEntry entry = m_PingLog.Get(i);
			res.read.ncell.Insert(entry.m_Token);
			res.read.ncell.Insert(entry.m_RecvMs);
			res.read.ncell.Insert(i);
			i = i + 1;
		}
	}

	void DoEmitLogPage(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		float pageF;
		if (!GetNum(args, "page_n", pageF) || !m_Probe.IsIntF(pageF))
		{
			Reject(res, "bad_args");
			return;
		}
		int total = m_Probe.EmitLogCount();
		int pagesN;
		int startRow;
		int endRow;
		if (!PageRange(total, 40, (int)pageF, pagesN, startRow, endRow))
		{
			Reject(res, "bad_args");
			return;
		}
		res.read.has.Insert("payload");
		res.read.nk.Insert("page_n");
		res.read.nk.Insert("pages_n");
		res.read.nk.Insert("rows_total_n");
		res.read.nv.Insert(pageF);
		res.read.nv.Insert(pagesN);
		res.read.nv.Insert(total);
		res.read.ncol.Insert("seq_n");
		res.read.ncol.Insert("tick_ms");
		res.read.ncol.Insert("lease_age_ms");
		res.read.ncol.Insert("idx_n");
		res.read.scol.Insert("op_id");
		res.read.scol.Insert("outcome");
		res.read.rows = endRow - startRow;
		int i = startRow;
		while (i < endRow)
		{
			DSBX_QA_EmitEntry entry = m_Probe.EmitLogEntry(i);
			res.read.ncell.Insert(entry.m_Seq);
			res.read.ncell.Insert(entry.m_TickMs);
			res.read.ncell.Insert(entry.m_LeaseAgeMs);
			res.read.ncell.Insert(i);
			res.read.scell.Insert(entry.m_OpId);
			res.read.scell.Insert(entry.m_Outcome);
			i = i + 1;
		}
	}

	void DoEffectStart(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		float periodF;
		float countF;
		float token0F;
		string clientInst;
		if (!GetNum(args, "period_ms", periodF) || !GetNum(args, "count_n", countF) || !GetNum(args, "token0_n", token0F) || !GetStr(args, "client_inst", clientInst))
		{
			Reject(res, "bad_args");
			return;
		}
		if (!m_Probe.IsFiniteF(periodF) || periodF < 100.0 || !m_Probe.IsIntF(countF) || countF < 1.0 || !m_Probe.IsIntF(token0F) || token0F <= 0.0 || clientInst == "")
		{
			Reject(res, "bad_args");
			return;
		}
		// Testigo de BASE-11 (W4) sobre el recurso qa_effect: witness_b opcional (0 o 1) y armado por defecto,
		// igual que _op_effect_start de qa/fake_ext_base.py.
		float effWitnessF = 1.0;
		bool effHasWitness = GetNum(args, "witness_b", effWitnessF);
		if (!effHasWitness)
		{
			effWitnessF = 1.0;
		}
		if (effWitnessF != 0.0 && effWitnessF != 1.0)
		{
			Reject(res, "bad_args");
			return;
		}
		string err = m_Jobs.StartJob(this, op.op_id, "qa_effect", m_EffectNcol, m_EffectScol, 20, 4096, 900000.0, "stop");
		if (err != "")
		{
			Reject(res, err);
			return;
		}
		// El efecto aplica su hombre muerto en su cadencia (fila blocked_lease antes de terminar), así que el gestor
		// no lo termina por su cuenta: igual que configure_job_faults(..., ext_handles_deadman=True) del peer falso.
		DSBX_QA_Job effJob = m_Jobs.GetJob(op.op_id);
		if (effJob)
		{
			effJob.m_ExtHandlesDeadman = true;
		}
		string fault = m_Probe.GetOpFault();
		m_EffectIgnore = fault == "ignore_deadman";
		m_EffectSkip = fault == "skip_send";
		m_EffectActive = true;
		m_EffectJobId = op.op_id;
		m_EffectPeriodMs = periodF;
		m_EffectCount = (int)countF;
		m_EffectToken0 = (int)token0F;
		m_EffectClientInst = clientInst;
		m_EffectDtsumMs = 0.0;
		m_EffectNextMs = 0.0;
		m_EffectSent = 0;
		if (effWitnessF == 1.0)
		{
			ArmWitness(op.op_id, "qa_effect");
		}
		m_Jobs.FillStartRead(res.read, op.op_id, "qa_effect");
	}

	void TickTimerRun(DSBX_QA_TimerRun run, float timeslice)
	{
		// Igual que el bucle de active_timers de qa/fake_ext_base.py.
		if (!run.m_Active)
		{
			return;
		}
		if (m_Jobs.GetState(run.m_JobId) != "running")
		{
			run.m_Active = false;
			return;
		}
		if (run.m_Freeze && m_Probe.IsTransportWaiting())
		{
			return;
		}
		run.m_DtsumMs = run.m_DtsumMs + timeslice * 1000.0;
		if (run.m_DtsumMs >= run.m_DurationMs)
		{
			array<float> fvals = new array<float>();
			fvals.Insert(run.m_Seq);
			fvals.Insert(m_Probe.m_Frame);
			fvals.Insert(m_Probe.NowMs());
			fvals.Insert(run.m_DtsumMs);
			array<string> fsvals = new array<string>();
			run.m_Seq = run.m_Seq + 1;
			if (m_Jobs.AppendRow(run.m_JobId, fvals, fsvals))
			{
				m_Jobs.EndJob(run.m_JobId, "done", "");
			}
			return;
		}
		if (run.m_DtsumMs >= run.m_NextMs)
		{
			array<float> nvals = new array<float>();
			nvals.Insert(run.m_Seq);
			nvals.Insert(m_Probe.m_Frame);
			nvals.Insert(m_Probe.NowMs());
			nvals.Insert(run.m_DtsumMs);
			array<string> svals = new array<string>();
			run.m_Seq = run.m_Seq + 1;
			if (!m_Jobs.AppendRow(run.m_JobId, nvals, svals))
			{
				return;
			}
			if (run.m_StepMs > 0.0)
			{
				run.m_NextMs = run.m_NextMs + run.m_StepMs;
			}
			else
			{
				run.m_NextMs = run.m_DtsumMs;
			}
		}
	}

	void TickEffect(float timeslice)
	{
		// Igual que el bucle de active_effects de qa/fake_ext_base.py: como mucho una emisión por tick.
		if (!m_EffectActive)
		{
			return;
		}
		if (m_Jobs.GetState(m_EffectJobId) != "running")
		{
			m_EffectActive = false;
			return;
		}
		m_EffectDtsumMs = m_EffectDtsumMs + timeslice * 1000.0;
		if (m_EffectDtsumMs < m_EffectNextMs)
		{
			return;
		}
		float tickNow = m_Probe.NowMs();
		float leaseAge = m_Probe.LeaseAgeMs();
		int token = m_EffectToken0 + m_EffectSent;
		// Hombre muerto (F02-H3): se comprueba antes de cada emisión; el mutante ignore_deadman no lo mira.
		if (!m_EffectIgnore && m_Jobs.IsDeadmanTripped(m_EffectJobId))
		{
			array<float> bvals = new array<float>();
			bvals.Insert(token);
			bvals.Insert(tickNow);
			bvals.Insert(leaseAge);
			array<string> bsvals = new array<string>();
			bsvals.Insert("blocked_lease");
			m_Jobs.AppendRow(m_EffectJobId, bvals, bsvals);
			m_Jobs.EndJob(m_EffectJobId, "failed", "lease_expired");
			return;
		}
		if (!m_EffectSkip)
		{
			SendPing(token, m_EffectClientInst);
		}
		array<float> evals = new array<float>();
		evals.Insert(token);
		evals.Insert(tickNow);
		evals.Insert(leaseAge);
		array<string> esvals = new array<string>();
		esvals.Insert("sent");
		bool appended = m_Jobs.AppendRow(m_EffectJobId, evals, esvals);
		m_EffectSent = m_EffectSent + 1;
		m_EffectNextMs = m_EffectNextMs + m_EffectPeriodMs;
		if (appended && m_EffectSent >= m_EffectCount)
		{
			m_Jobs.EndJob(m_EffectJobId, "done", "");
		}
	}

	void TryArmedWitness()
	{
		// Testigo B (N4, W4): intenta arrancar en cada tick, sin depender de HTTP.
		if (!m_WitnessArmed)
		{
			return;
		}
		m_WitnessAttemptsN = m_WitnessAttemptsN + 1;
		string werr = m_Jobs.StartJob(this, m_WitnessJobId, m_WitnessResource, m_TimerNcol, m_NoScol, 20, 4096, 900000.0, "continue");
		if (werr != "")
		{
			return;
		}
		DSBX_QA_Job wjob = m_Jobs.GetJob(m_WitnessJobId);
		if (wjob)
		{
			// §13 A2: la marca del testigo es el start_tick_ms que guardó el gestor, sin segunda lectura del reloj.
			m_WitnessStartedTickMs = wjob.m_StartTickMs;
		}
		m_WitnessArmed = false;
		m_WitnessRun.Begin(m_WitnessJobId, 200.0, 50.0, false);
	}

	override void OnTick(float timeslice)
	{
		// Orden de qa/fake_ext_base.py: temporizadores, efecto y, al final, el intento del testigo.
		m_TicksN = m_TicksN + 1;
		TickTimerRun(m_TimerRun, timeslice);
		TickTimerRun(m_WitnessRun, timeslice);
		TickEffect(timeslice);
		TryArmedWitness();
	}

	override void OnJobEnd(string job_id, string state, string reason)
	{
		m_EndCallsN = m_EndCallsN + 1;
		m_LastEndJob = job_id;
		m_LastEndState = state;
		m_LastEndReason = reason;
		if (job_id == m_TimerRun.m_JobId)
		{
			m_TimerRun.m_Active = false;
		}
		if (job_id == m_WitnessRun.m_JobId)
		{
			m_WitnessRun.m_Active = false;
		}
		if (job_id == m_EffectJobId)
		{
			m_EffectActive = false;
		}
	}

	override void OnRpc(PlayerIdentity sender, Object target, int rpc_type, ParamsReadContext ctx)
	{
		if (rpc_type != DSBX_QA_RPC_BASE_PING)
		{
			return;
		}
		int token = 0;
		string clientInst = "";
		if (!ctx.Read(token))
		{
			return;
		}
		if (!ctx.Read(clientInst))
		{
			return;
		}
		if (clientInst != m_Probe.GetInst())
		{
			return;
		}
		DSBX_QA_PingEntry entry = new DSBX_QA_PingEntry();
		entry.m_Token = token;
		entry.m_RecvMs = m_Probe.NowMs();
		m_PingLog.Insert(entry);
		while (m_PingLog.Count() > 512)
		{
			m_PingLog.RemoveOrdered(0);
		}
		if (m_Probe.LeaseOk())
		{
			m_RpcPingCount = m_RpcPingCount + 1;
			m_RpcLastToken = token;
		}
	}

	override void OnShutdown()
	{
		m_TimerRun.m_Active = false;
		m_WitnessRun.m_Active = false;
		m_EffectActive = false;
		m_WitnessArmed = false;
	}
}

