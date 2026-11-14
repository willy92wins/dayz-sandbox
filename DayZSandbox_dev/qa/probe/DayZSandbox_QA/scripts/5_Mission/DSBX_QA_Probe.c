const int DSBX_QA_RPC_CAM = 26102701;
const int DSBX_QA_WIRE_CAP = 3500;

class DSBX_QA_Callback : RestCallback
{
	DSBX_QA_Probe m_Probe;
	int m_Kind;
	int m_Gen;
	bool m_Done;

	void DSBX_QA_Callback(DSBX_QA_Probe probe)
	{
		m_Probe = probe;
		m_Kind = 0;
		m_Gen = 0;
		m_Done = true;
	}

	void Arm(DSBX_QA_Probe probe, int kind, int gen)
	{
		m_Probe = probe;
		m_Kind = kind;
		m_Gen = gen;
		m_Done = false;
	}

	void Retire()
	{
		m_Done = true;
	}

	void Detach()
	{
		m_Probe = null;
		m_Done = true;
	}

	override void OnSuccess(string data, int dataSize)
	{
		if (m_Done)
		{
			return;
		}
		m_Done = true;
		DSBX_QA_Probe probe = m_Probe;
		if (probe)
		{
			probe.OnHttpDone(this, m_Kind, m_Gen, true, data, 0, false);
		}
	}

	override void OnError(int errorCode)
	{
		if (m_Done)
		{
			return;
		}
		m_Done = true;
		DSBX_QA_Probe probe = m_Probe;
		if (probe)
		{
			probe.OnHttpDone(this, m_Kind, m_Gen, false, "", errorCode, false);
		}
	}

	override void OnTimeout()
	{
		if (m_Done)
		{
			return;
		}
		m_Done = true;
		DSBX_QA_Probe probe = m_Probe;
		if (probe)
		{
			probe.OnHttpDone(this, m_Kind, m_Gen, false, "", 0, true);
		}
	}
}

class DSBX_QA_EmitEntry : Managed
{
	string m_OpId;
	int m_Seq;
	float m_TickMs;
	float m_LeaseAgeMs;
	string m_Outcome;

	void DSBX_QA_EmitEntry()
	{
		m_OpId = "";
		m_Seq = 0;
		m_TickMs = 0.0;
		m_LeaseAgeMs = 0.0;
		m_Outcome = "";
	}
}

class DSBX_QA_Probe : Managed
{
	const int ST_WAIT = 0;
	const int ST_HELLO = 1;
	const int ST_READY = 2;
	const int ST_POLL = 3;
	const int ST_PROCESS = 4;
	const int ST_SEND = 5;
	const int KIND_HELLO = 1;
	const int KIND_POLL = 2;
	const int KIND_RESULT = 3;
	const int KIND_KEEPALIVE = 4;
	const int CALLBACK_POOL_MAX = 4;

	static DSBX_QA_Probe s_ClientProbe;
	static DSBX_QA_Probe s_ServerProbe;

	string m_Role;
	bool m_IsClient;
	string m_Inst;
	int m_Frame;
	string m_Key;
	string m_Url;
	int m_RetryMs;
	int m_WaitRetryMs;
	RestContext m_Ctx;
	string m_CtxUrl;
	int m_LeaseMs;
	float m_LastOkPollMs;
	bool m_HasLastOk;
	int m_State;
	int m_FailCount;
	float m_NextTryMs;
	bool m_HadSuccess;
	bool m_ShutdownDone;
	bool m_LogCfgUsable;
	string m_LogCfgReason;
	ref DSBX_QA_Callback m_PollCallback;
	ref array<ref DSBX_QA_Callback> m_CallbackPool;
	DSBX_QA_Callback m_ActiveCb;
	int m_ActiveKind;
	int m_ActiveGen;
	int m_NextGen;
	float m_ActiveSentMs;
	ref array<ref DSBX_QA_Op> m_Ops;
	float m_BatchNowMs;
	float m_BatchRecvMs;
	int m_OpIndex;
	ref array<ref DSBX_QA_Result> m_Bucket;
	ref map<string, ref DSBX_QA_Result> m_Cache;
	ref array<string> m_CacheOrder;
	ref array<ref DSBX_QA_RpcEntry> m_RpcLog;
	bool m_HasSeq;
	int m_LastSeq;
	Camera m_Camera;
	bool m_FogFrozen;
	bool m_JobActive;
	DSBX_QA_Op m_JobOp;
	DSBX_QA_Args m_JobArgs;
	float m_JobRecvMs;
	int m_JobFrameRecv;
	float m_JobStartMs;
	float m_JobFogTarget;
	int m_BurstIndex;
	int m_SendIndex;
	int m_SendFailures;
	float m_SendNextMs;
	bool m_HasPendingPose;
	ref array<float> m_PendingPos;
	ref array<float> m_PendingYpr;
	ref DSBX_QA_JobMgr m_Jobs;
	ref array<ref DSBX_QA_Ext> m_Exts;
	float m_DtSumMs;
	string m_OpFault;
	int m_CallbackBudget;
	int m_CallbacksCreatedN;
	bool m_BudgetLogged;
	bool m_BudgetExhausted;
	ref map<string, string> m_ResultVerb;
	ref array<ref DSBX_QA_EmitEntry> m_EmitLog;
	ref array<string> m_CacheSnapOrder;
	string m_CacheSnapId;
	float m_KeepaliveNextMs;

	void DSBX_QA_Probe(string role)
	{
		m_Role = role;
		m_IsClient = role == "client";
		m_Frame = 0;
		m_Url = "";
		m_RetryMs = 2000;
		m_WaitRetryMs = 2000;
		m_Ctx = null;
		m_CtxUrl = "";
		m_LeaseMs = 3000;
		m_LastOkPollMs = 0.0;
		m_HasLastOk = false;
		m_State = ST_WAIT;
		m_FailCount = 0;
		m_NextTryMs = 0.0;
		m_HadSuccess = false;
		m_ShutdownDone = false;
		m_LogCfgUsable = false;
		m_LogCfgReason = "";
		m_PollCallback = null;
		m_CallbackPool = new array<ref DSBX_QA_Callback>();
		m_ActiveCb = null;
		m_ActiveKind = 0;
		m_ActiveGen = 0;
		m_NextGen = 0;
		m_ActiveSentMs = 0.0;
		m_Ops = null;
		m_BatchNowMs = 0.0;
		m_BatchRecvMs = 0.0;
		m_OpIndex = 0;
		m_Bucket = new array<ref DSBX_QA_Result>();
		m_Cache = new map<string, ref DSBX_QA_Result>();
		m_CacheOrder = new array<string>();
		m_RpcLog = new array<ref DSBX_QA_RpcEntry>();
		m_HasSeq = false;
		m_LastSeq = 0;
		m_Camera = null;
		m_FogFrozen = false;
		m_JobActive = false;
		m_JobOp = null;
		m_JobArgs = null;
		m_JobRecvMs = 0.0;
		m_JobFrameRecv = 0;
		m_JobStartMs = 0.0;
		m_JobFogTarget = 0.0;
		m_BurstIndex = 0;
		m_SendIndex = 0;
		m_SendFailures = 0;
		m_SendNextMs = 0.0;
		m_HasPendingPose = false;
		m_PendingPos = null;
		m_PendingYpr = null;
		m_DtSumMs = 0.0;
		m_OpFault = "";
		m_CallbackBudget = 2000;
		m_CallbacksCreatedN = 0;
		m_BudgetLogged = false;
		m_BudgetExhausted = false;
		m_ResultVerb = new map<string, string>();
		m_EmitLog = new array<ref DSBX_QA_EmitEntry>();
		m_CacheSnapOrder = new array<string>();
		m_CacheSnapId = "";
		m_KeepaliveNextMs = 0.0;
		m_Jobs = new DSBX_QA_JobMgr(this);
		m_Exts = new array<ref DSBX_QA_Ext>();
		m_Exts.Insert(new DSBX_QA_X_Persist());
		m_Exts.Insert(new DSBX_QA_X_Actor());
		m_Exts.Insert(new DSBX_QA_X_Cam());
		m_Exts.Insert(new DSBX_QA_X_Cot());
		m_Exts.Insert(new DSBX_QA_X_Env());
		m_Exts.Insert(new DSBX_QA_X_Take());
		m_Exts.Insert(new DSBX_QA_X_Perf());
		m_Exts.Insert(new DSBX_QA_X_Map());
		m_Exts.Insert(new DSBX_QA_X_Base());
		int ei = 0;
		while (ei < m_Exts.Count())
		{
			m_Exts.Get(ei).Init(this);
			ei = ei + 1;
		}
		int uuid[4];
		UUIDApi.Generate(uuid);
		string raw = UUIDApi.FormatString(uuid);
		string partA = raw.Substring(0, 8);
		string partB = raw.Substring(9, 4);
		string partC = raw.Substring(14, 4);
		string partD = raw.Substring(19, 4);
		string partE = raw.Substring(24, 12);
		string inst = partA + partB + partC + partD + partE;
		inst.ToLower();
		m_Inst = inst;
		if (m_IsClient)
		{
			s_ClientProbe = this;
		}
		else
		{
			s_ServerProbe = this;
		}
		DayZGame.Event_OnRPC.Insert(DSBX_QA_Probe.OnAnyRpc);
	}

	void ~DSBX_QA_Probe()
	{
		Shutdown();
	}

	void Shutdown()
	{
		if (m_ShutdownDone)
		{
			return;
		}
		m_ShutdownDone = true;
		if (m_Jobs)
		{
			m_Jobs.ShutdownJobs();
		}
		if (m_Exts)
		{
			int ei = 0;
			while (ei < m_Exts.Count())
			{
				m_Exts.Get(ei).OnShutdown();
				ei = ei + 1;
			}
		}
		DayZGame.Event_OnRPC.Remove(DSBX_QA_Probe.OnAnyRpc);
		if (s_ClientProbe == this)
		{
			s_ClientProbe = null;
		}
		if (s_ServerProbe == this)
		{
			s_ServerProbe = null;
		}
		if (m_Camera && g_Game)
		{
			g_Game.ObjectDelete(m_Camera);
		}
		m_Camera = null;
		if (m_ActiveCb)
		{
			m_ActiveCb.Detach();
		}
		m_ActiveCb = null;
		m_ActiveKind = 0;
		m_ActiveGen = 0;
		if (m_PollCallback)
		{
			m_PollCallback.Detach();
		}
		m_PollCallback = null;
		int i = 0;
		while (i < m_CallbackPool.Count())
		{
			DSBX_QA_Callback pooledCb = m_CallbackPool.Get(i);
			if (pooledCb)
			{
				pooledCb.Detach();
			}
			i = i + 1;
		}
		m_CallbackPool.Clear();
		Log("shutdown");
	}

	void Log(string msg)
	{
		Print("[DSBX_QA] " + msg);
	}

	float NowMs()
	{
		return g_Game.GetTickTime() * 1000.0;
	}

	float AbsF(float value)
	{
		if (value < 0.0)
		{
			return -value;
		}
		return value;
	}

	bool IsFiniteF(float value)
	{
		if (value != value)
		{
			return false;
		}
		if (AbsF(value) > 300000000000000000000000000000000000000.0)
		{
			return false;
		}
		return true;
	}

	bool IsIntF(float value)
	{
		if (!IsFiniteF(value))
		{
			return false;
		}
		int iv = (int)value;
		return (float)iv == value;
	}

	string BuildName()
	{
#ifdef DIAG_DEVELOPER
		return "diag";
#else
		return "retail";
#endif
	}

	string KeyQuery()
	{
		return "key=" + m_Key;
	}

	string HelloBody()
	{
		string body = "{\"proto\":\"qa0\",\"peer\":\"" + m_Role + "\",\"inst\":\"" + m_Inst + "\",\"build\":\"" + BuildName() + "\",\"probe_ver\":\"dsbx-qa1+" + DSBX_QA_STAMP + "\"}";
		return body;
	}

	string GetInst()
	{
		return m_Inst;
	}

	string GetRole()
	{
		return m_Role;
	}

	string GetOpFault()
	{
		return m_OpFault;
	}

	bool IsTransportWaiting()
	{
		return m_State == ST_WAIT || m_State == ST_HELLO;
	}

	float LeaseAgeMs()
	{
		if (!m_HasLastOk)
		{
			return 1000000000.0;
		}
		return NowMs() - m_LastOkPollMs;
	}

	int GetLeaseMs()
	{
		return m_LeaseMs;
	}

	bool LeaseOk()
	{
		if (!m_HasLastOk)
		{
			return false;
		}
		return LeaseAgeMs() <= m_LeaseMs;
	}

	int CallbacksCreatedN()
	{
		return m_CallbacksCreatedN;
	}

	int CallbacksPooledN()
	{
		return m_CallbackPool.Count();
	}

	int CallbacksInflightN()
	{
		if (m_ActiveCb)
		{
			return 1;
		}
		return 0;
	}

	int CallbackBudgetN()
	{
		return m_CallbackBudget;
	}

	int CacheSizeN()
	{
		return m_CacheOrder.Count();
	}

	int RpcLogSizeN()
	{
		return m_RpcLog.Count();
	}

	int JobsLiveN()
	{
		if (m_Jobs)
		{
			return m_Jobs.LiveCount();
		}
		return 0;
	}

	void QaCacheFill(int n, string fillId)
	{
		int i = 0;
		while (i < n)
		{
			DSBX_QA_Result syn = new DSBX_QA_Result();
			syn.op_id = fillId + "-" + i;
			syn.status = "done";
			syn.reason = "";
			syn.dup = 0;
			syn.recv_ms = NowMs();
			syn.done_ms = NowMs();
			syn.frame_recv = m_Frame;
			syn.frame_done = m_Frame;
			CachePut(syn);
			i = i + 1;
		}
	}

	int QaCacheSnapshot(string snapId)
	{
		m_CacheSnapOrder = new array<string>();
		int i = 0;
		while (i < m_CacheOrder.Count())
		{
			m_CacheSnapOrder.Insert(m_CacheOrder.Get(i));
			i = i + 1;
		}
		m_CacheSnapId = snapId;
		return m_CacheSnapOrder.Count();
	}

	string CacheSnapId()
	{
		return m_CacheSnapId;
	}

	int CacheSnapCount()
	{
		return m_CacheSnapOrder.Count();
	}

	string CacheSnapOpId(int idx)
	{
		return m_CacheSnapOrder.Get(idx);
	}

	DSBX_QA_RpcEntry RpcLogEntry(int idx)
	{
		return m_RpcLog.Get(idx);
	}

	int EmitLogCount()
	{
		return m_EmitLog.Count();
	}

	DSBX_QA_EmitEntry EmitLogEntry(int idx)
	{
		return m_EmitLog.Get(idx);
	}

	void AddEmitEntry(string opId, int seq, string outcome)
	{
		DSBX_QA_EmitEntry entry = new DSBX_QA_EmitEntry();
		entry.m_OpId = opId;
		entry.m_Seq = seq;
		entry.m_TickMs = NowMs();
		entry.m_LeaseAgeMs = LeaseAgeMs();
		entry.m_Outcome = outcome;
		m_EmitLog.Insert(entry);
		while (m_EmitLog.Count() > 512)
		{
			m_EmitLog.RemoveOrdered(0);
		}
	}

	bool UrlUsable(string url)
	{
		string prefix = "http://127.0.0.1:";
		string digitsOk = "0123456789";
		if (url.Length() <= prefix.Length())
		{
			return false;
		}
		if (url.Substring(0, prefix.Length()) != prefix)
		{
			return false;
		}
		string rest = url.Substring(prefix.Length(), url.Length() - prefix.Length());
		if (rest.Length() < 2)
		{
			return false;
		}
		if (rest.Substring(rest.Length() - 1, 1) != "/")
		{
			return false;
		}
		string digits = rest.Substring(0, rest.Length() - 1);
		if (digits.Length() < 1 || digits.Length() > 5)
		{
			return false;
		}
		int port = 0;
		int i = 0;
		while (i < digits.Length())
		{
			string ch = digits.Substring(i, 1);
			if (digitsOk.IndexOf(ch) < 0)
			{
				return false;
			}
			port = port * 10 + ch.ToInt();
			i = i + 1;
		}
		if (port < 1 || port > 65535)
		{
			return false;
		}
		return true;
	}

	bool LoadConfig()
	{
		DSBX_QA_Config cfg;
		string loadErr;
		bool loaded = JsonFileLoader<DSBX_QA_Config>.LoadFile("$profile:dsbx_qa.json", cfg, loadErr);
		bool usable = false;
		string reason = "missing";
		int retry = 2000;
		int budget = 2000;
		string newUrl = "";
		if (loaded && cfg)
		{
			retry = cfg.retry_ms;
			if (retry <= 0)
			{
				retry = 2000;
			}
			budget = cfg.callback_budget;
			if (budget <= 0)
			{
				budget = 2000;
			}
			newUrl = cfg.url;
			if (cfg.key == "")
			{
				reason = "empty_key";
			}
			else if (!UrlUsable(newUrl))
			{
				reason = "bad_url";
			}
			else
			{
				usable = true;
				reason = "ok";
			}
		}
		m_CallbackBudget = budget;
		m_WaitRetryMs = retry;
		if (usable)
		{
			RestApi api = GetRestApi();
			if (!api)
			{
				api = CreateRestApi();
			}
			if (!api)
			{
				usable = false;
				reason = "no_rest";
			}
			else if (m_CtxUrl != newUrl || !m_Ctx)
			{
				RestContext ctx = api.GetRestContext(newUrl);
				if (!ctx)
				{
					usable = false;
					reason = "no_context";
				}
				else
				{
					ctx.SetHeader("application/json");
					m_Ctx = ctx;
					m_CtxUrl = newUrl;
				}
			}
		}
		if (usable)
		{
			m_Url = newUrl;
			m_Key = cfg.key;
			m_RetryMs = retry;
		}
		if (usable != m_LogCfgUsable || reason != m_LogCfgReason)
		{
			m_LogCfgUsable = usable;
			m_LogCfgReason = reason;
			if (usable)
			{
				Log("config usable");
			}
			else if (reason == "bad_url")
			{
				Log("config not usable: bad url");
			}
			else if (reason == "empty_key")
			{
				Log("config not usable: empty key");
			}
			else if (reason == "no_rest")
			{
				Log("config not usable: rest unavailable");
			}
			else if (reason == "no_context")
			{
				Log("config not usable: context unavailable");
			}
			else
			{
				Log("config not usable: missing or unreadable");
			}
		}
		return usable;
	}

	void NoteBudgetReached()
	{
		m_BudgetExhausted = true;
		if (!m_BudgetLogged)
		{
			m_BudgetLogged = true;
			Log("callback_budget_exhausted created_n=" + m_CallbacksCreatedN + " budget_n=" + m_CallbackBudget);
		}
	}

	DSBX_QA_Callback AcquireCallback(int kind)
	{
		if (m_BudgetExhausted)
		{
			return null;
		}
		DSBX_QA_Callback cb = null;
		bool created = false;
		if (kind == KIND_POLL)
		{
			if (!m_PollCallback)
			{
				if (m_CallbacksCreatedN >= m_CallbackBudget)
				{
					NoteBudgetReached();
					return null;
				}
				m_PollCallback = new DSBX_QA_Callback(this);
				created = true;
			}
			cb = m_PollCallback;
		}
		else
		{
			int last = m_CallbackPool.Count() - 1;
			if (last >= 0)
			{
				cb = m_CallbackPool.Get(last);
				m_CallbackPool.RemoveOrdered(last);
			}
			else
			{
				if (m_CallbacksCreatedN >= m_CallbackBudget)
				{
					NoteBudgetReached();
					return null;
				}
				cb = new DSBX_QA_Callback(this);
				created = true;
			}
		}
		if (created)
		{
			m_CallbacksCreatedN = m_CallbacksCreatedN + 1;
			if (m_CallbacksCreatedN >= m_CallbackBudget)
			{
				NoteBudgetReached();
			}
		}
		m_NextGen = m_NextGen + 1;
		cb.Arm(this, kind, m_NextGen);
		m_ActiveCb = cb;
		m_ActiveKind = kind;
		m_ActiveGen = m_NextGen;
		m_ActiveSentMs = NowMs();
		return cb;
	}

	void SettleCallback(DSBX_QA_Callback cb, int kind, bool success)
	{
		if (kind == KIND_POLL)
		{
			if (!success && m_PollCallback == cb)
			{
				m_PollCallback = null;
				cb.Retire();
			}
			return;
		}
		if (success)
		{
			if (m_CallbackPool.Count() < CALLBACK_POOL_MAX)
			{
				m_CallbackPool.Insert(cb);
			}
			return;
		}
		cb.Retire();
	}

	void LogResultAbandoned(string opId, string motivo)
	{
		Log("result abandoned " + opId + " " + motivo);
	}

	void RegisterFailure(bool isTimeout, int errorCode)
	{
		if (m_HadSuccess)
		{
			if (isTimeout)
			{
				Log("failure after success: timeout");
			}
			else
			{
				Log("failure after success: error " + errorCode);
			}
			m_HadSuccess = false;
		}
		m_FailCount = m_FailCount + 1;
		float wait = 250.0;
		int i = 1;
		while (i < m_FailCount)
		{
			wait = wait * 2.0;
			i = i + 1;
		}
		if (wait > m_RetryMs)
		{
			wait = m_RetryMs;
		}
		m_NextTryMs = NowMs() + wait;
		m_State = ST_WAIT;
	}

	void SendHello()
	{
		DSBX_QA_Callback cb = AcquireCallback(KIND_HELLO);
		if (!cb)
		{
			m_State = ST_WAIT;
			m_NextTryMs = NowMs() + m_RetryMs;
			return;
		}
		m_State = ST_HELLO;
		m_Ctx.POST(cb, "hello?" + KeyQuery(), HelloBody());
	}

	void SendPoll()
	{
		DSBX_QA_Callback cb = AcquireCallback(KIND_POLL);
		if (!cb)
		{
			m_State = ST_WAIT;
			m_NextTryMs = NowMs() + m_RetryMs;
			return;
		}
		m_State = ST_POLL;
		m_Ctx.GET(cb, "poll?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&frame=" + m_Frame + "&tick_s=" + g_Game.GetTickTime());
	}

	void SendKeepalive()
	{
		DSBX_QA_Callback cb = AcquireCallback(KIND_KEEPALIVE);
		if (!cb)
		{
			return;
		}
		m_Ctx.GET(cb, "poll?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&frame=" + m_Frame + "&tick_s=" + g_Game.GetTickTime() + "&deliver=0");
	}

	void OnHttpDone(DSBX_QA_Callback cb, int kind, int gen, bool success, string data, int errorCode, bool isTimeout)
	{
		if (m_ShutdownDone)
		{
			return;
		}
		if (cb != m_ActiveCb || kind != m_ActiveKind || gen != m_ActiveGen)
		{
			return;
		}
		m_ActiveCb = null;
		m_ActiveKind = 0;
		m_ActiveGen = 0;
		SettleCallback(cb, kind, success);
		float now = NowMs();
		if (kind == KIND_KEEPALIVE)
		{
			// Un keepalive fallido no cambia m_State: la orden F0.2 en curso y el resto del lote siguen;
			// el lease caduca solo si no llega ningún 200, y el flujo normal (resultados, poll) gestiona el fallo.
			if (!success)
			{
				m_KeepaliveNextMs = now + 500.0;
				return;
			}
			JsonSerializer kaSer = new JsonSerializer();
			string kaErr;
			DSBX_QA_PollResp kaResp = new DSBX_QA_PollResp();
			bool kaParsed = kaSer.ReadFromString(kaResp, data, kaErr);
			if (!kaParsed || !kaResp.ops || !IsFiniteF(kaResp.now_ms))
			{
				m_KeepaliveNextMs = now + 500.0;
				return;
			}
			m_FailCount = 0;
			m_HadSuccess = true;
			m_LastOkPollMs = now;
			m_HasLastOk = true;
			return;
		}
		if (kind == KIND_RESULT)
		{
			if (success)
			{
				JsonSerializer ackSer = new JsonSerializer();
				string ackErr;
				DSBX_QA_AckResp ackResp = new DSBX_QA_AckResp();
				bool ackParsed = ackSer.ReadFromString(ackResp, data, ackErr);
				if (!ackParsed || !ackResp.ok)
				{
					ResultFailed(now, false);
					return;
				}
				m_SendIndex = m_SendIndex + 1;
				m_SendFailures = 0;
				m_SendNextMs = 0.0;
			}
			else
			{
				ResultFailed(now, false);
			}
			return;
		}
		if (!success)
		{
			RegisterFailure(isTimeout, errorCode);
			return;
		}
		JsonSerializer serializer = new JsonSerializer();
		string parseErr;
		if (kind == KIND_HELLO)
		{
			DSBX_QA_HelloResp resp = new DSBX_QA_HelloResp();
			bool parsed = serializer.ReadFromString(resp, data, parseErr);
			if (!parsed || !resp.ok || resp.lease_ms <= 0)
			{
				RegisterFailure(false, 0);
				return;
			}
			m_LeaseMs = resp.lease_ms;
			m_FailCount = 0;
			m_HadSuccess = true;
			Log("hello accepted");
			m_State = ST_READY;
			return;
		}
		DSBX_QA_PollResp pollResp = new DSBX_QA_PollResp();
		bool pollParsed = serializer.ReadFromString(pollResp, data, parseErr);
		if (!pollParsed || !pollResp.ops || !IsFiniteF(pollResp.now_ms))
		{
			RegisterFailure(false, 0);
			return;
		}
		m_FailCount = 0;
		m_HadSuccess = true;
		m_LastOkPollMs = now;
		m_HasLastOk = true;
		if (m_Jobs)
		{
			m_Jobs.CompleteDeferredEnds();
		}
		m_Ops = pollResp.ops;
		m_BatchNowMs = pollResp.now_ms;
		m_BatchRecvMs = now;
		m_OpIndex = 0;
		m_JobActive = false;
		m_JobOp = null;
		m_Bucket = new array<ref DSBX_QA_Result>();
		m_State = ST_PROCESS;
	}

	void ResultFailed(float now, bool serializeFailed)
	{
		m_SendFailures = m_SendFailures + 1;
		if (m_SendFailures >= 4)
		{
			string motivo = "p6_exhausted";
			if (serializeFailed)
			{
				motivo = "serialize_failed";
			}
			if (m_Bucket && m_SendIndex >= 0 && m_SendIndex < m_Bucket.Count())
			{
				DSBX_QA_Result abandonedRes = m_Bucket.Get(m_SendIndex);
				LogResultAbandoned(abandonedRes.op_id, motivo);
			}
			m_SendIndex = m_SendIndex + 1;
			m_SendFailures = 0;
			m_SendNextMs = 0.0;
			return;
		}
		float gap = 250.0;
		int i = 1;
		while (i < m_SendFailures)
		{
			gap = gap * 2.0;
			i = i + 1;
		}
		m_SendNextMs = now + gap;
	}

	void Watchdog(float now)
	{
		if (!m_ActiveCb)
		{
			return;
		}
		if (now - m_ActiveSentMs < 30000.0)
		{
			return;
		}
		DSBX_QA_Callback cb = m_ActiveCb;
		int kind = m_ActiveKind;
		m_ActiveCb = null;
		m_ActiveKind = 0;
		m_ActiveGen = 0;
		cb.Retire();
		if (kind == KIND_POLL && m_PollCallback == cb)
		{
			m_PollCallback = null;
		}
		if (kind == KIND_RESULT)
		{
			ResultFailed(now, false);
			return;
		}
		if (kind == KIND_HELLO || kind == KIND_POLL || kind == KIND_KEEPALIVE)
		{
			RegisterFailure(true, 0);
		}
	}

	void Tick(float timeslice)
	{
		if (m_ShutdownDone)
		{
			return;
		}
		m_Frame = m_Frame + 1;
		m_DtSumMs = m_DtSumMs + timeslice * 1000.0;
		float now = NowMs();
		ApplyPendingPose();
		Watchdog(now);
		if (m_ShutdownDone)
		{
			return;
		}
		if (m_Jobs)
		{
			m_Jobs.TickJobs(timeslice, now);
		}
		if (m_Exts)
		{
			int ei = 0;
			while (ei < m_Exts.Count())
			{
				m_Exts.Get(ei).OnTick(timeslice);
				ei = ei + 1;
			}
		}
		if (m_JobActive)
		{
			AdvanceJob(now);
			if (m_JobActive)
			{
				if (m_Bucket.Count() == 0 && !m_ActiveCb && now >= m_KeepaliveNextMs)
				{
					m_KeepaliveNextMs = now + 500.0;
					SendKeepalive();
				}
				return;
			}
			if (m_State != ST_PROCESS && m_Bucket.Count() > 0)
			{
				BeginSend();
				return;
			}
		}
		if (m_State == ST_WAIT)
		{
			if (now >= m_NextTryMs)
			{
				if (LoadConfig())
				{
					SendHello();
				}
				else
				{
					m_NextTryMs = NowMs() + m_WaitRetryMs;
				}
			}
			return;
		}
		if (m_State == ST_READY)
		{
			SendPoll();
			return;
		}
		if (m_State == ST_PROCESS)
		{
			ProcessStep(now);
			return;
		}
		if (m_State == ST_SEND)
		{
			SendStep(now);
			return;
		}
	}

	void BeginSend()
	{
		m_SendIndex = 0;
		m_SendFailures = 0;
		m_SendNextMs = 0.0;
		m_State = ST_SEND;
	}

	bool IsF02Verb(string verb)
	{
		if (verb == "srv_read" || verb == "ground_query" || verb == "ambient_set" || verb == "ambient_read" || verb == "rpc_burst" || verb == "cam_pose_set" || verb == "cam_pose_read" || verb == "rpc_log_read")
		{
			return true;
		}
		return false;
	}

	void SendStep(float now)
	{
		if (m_ActiveCb)
		{
			return;
		}
		if (now < m_SendNextMs)
		{
			return;
		}
		if (m_SendIndex >= m_Bucket.Count())
		{
			m_State = ST_READY;
			return;
		}
		DSBX_QA_Result res = m_Bucket.Get(m_SendIndex);
		JsonSerializer serializer = new JsonSerializer();
		string body;
		bool written = serializer.WriteToString(res, false, body);
		if (!written)
		{
			ResultFailed(now, true);
			return;
		}
		string dupOld = "\"dup\":0";
		string dupNew = "\"dup\":false";
		if (res.dup == 1)
		{
			dupOld = "\"dup\":1";
			dupNew = "\"dup\":true";
		}
		int dupPos = body.IndexOf(dupOld);
		int dupEnd = dupPos + dupOld.Length();
		if (dupPos < 0 || body.IndexOfFrom(dupEnd, dupOld) >= 0)
		{
			LogResultAbandoned(res.op_id, "dup_replace");
			m_SendIndex = m_SendIndex + 1;
			return;
		}
		string bodyHead = body.Substring(0, dupPos);
		string bodyRest = body.Substring(dupEnd, body.Length() - dupEnd);
		body = bodyHead + dupNew + bodyRest;
		string verbForRes = "";
		if (m_ResultVerb.Contains(res.op_id))
		{
			verbForRes = m_ResultVerb.Get(res.op_id);
		}
		if (verbForRes != "" && !IsF02Verb(verbForRes) && body.Length() > DSBX_QA_WIRE_CAP)
		{
			DSBX_QA_Result sub = new DSBX_QA_Result();
			sub.op_id = res.op_id;
			sub.status = "error";
			sub.reason = "result_too_large";
			sub.dup = res.dup;
			sub.recv_ms = res.recv_ms;
			sub.done_ms = res.done_ms;
			sub.frame_recv = res.frame_recv;
			sub.frame_done = res.frame_done;
			JsonSerializer subSer = new JsonSerializer();
			string subBody;
			bool subWritten = subSer.WriteToString(sub, false, subBody);
			if (!subWritten)
			{
				ResultFailed(now, true);
				return;
			}
			string subOld = "\"dup\":0";
			string subNew = "\"dup\":false";
			if (sub.dup == 1)
			{
				subOld = "\"dup\":1";
				subNew = "\"dup\":true";
			}
			int subPos = subBody.IndexOf(subOld);
			int subEnd = subPos + subOld.Length();
			if (subPos < 0 || subBody.IndexOfFrom(subEnd, subOld) >= 0)
			{
				LogResultAbandoned(res.op_id, "dup_replace");
				m_SendIndex = m_SendIndex + 1;
				return;
			}
			string subHead = subBody.Substring(0, subPos);
			string subRest = subBody.Substring(subEnd, subBody.Length() - subEnd);
			body = subHead + subNew + subRest;
			CachePut(sub);
		}
		DSBX_QA_Callback cb = AcquireCallback(KIND_RESULT);
		if (!cb)
		{
			return;
		}
		m_Ctx.POST(cb, "result?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst, body);
	}

	bool VerbForRole(string verb)
	{
		if (m_Role == "server")
		{
			if (verb == "srv_read" || verb == "ground_query" || verb == "ambient_set" || verb == "ambient_read" || verb == "rpc_burst")
			{
				return true;
			}
			return false;
		}
		if (verb == "cam_pose_set" || verb == "cam_pose_read" || verb == "rpc_log_read")
		{
			return true;
		}
		return false;
	}

	DSBX_QA_Result MakeResult(DSBX_QA_Op op, string status, string reason, float recvMs, int frameRecv)
	{
		DSBX_QA_Result res = new DSBX_QA_Result();
		res.op_id = op.op_id;
		res.status = status;
		res.reason = reason;
		res.dup = 0;
		res.recv_ms = recvMs;
		res.done_ms = NowMs();
		res.frame_recv = frameRecv;
		res.frame_done = m_Frame;
		return res;
	}

	void CachePut(DSBX_QA_Result res)
	{
		if (!m_Cache.Contains(res.op_id))
		{
			m_CacheOrder.Insert(res.op_id);
		}
		m_Cache.Set(res.op_id, res);
		while (m_CacheOrder.Count() > 1024)
		{
			string oldest = m_CacheOrder.Get(0);
			m_CacheOrder.RemoveOrdered(0);
			m_Cache.Remove(oldest);
		}
	}

	void FinishInstant(DSBX_QA_Result res)
	{
		CachePut(res);
		m_Bucket.Insert(res);
		m_OpIndex = m_OpIndex + 1;
	}

	void FinishJob(DSBX_QA_Result res)
	{
		CachePut(res);
		m_Bucket.Insert(res);
		m_JobActive = false;
		m_JobOp = null;
		m_JobArgs = null;
		m_OpIndex = m_OpIndex + 1;
	}

	void ProcessStep(float now)
	{
		while (true)
		{
			if (m_JobActive)
			{
				AdvanceJob(now);
				return;
			}
			if (!m_Ops || m_OpIndex >= m_Ops.Count())
			{
				BeginSend();
				return;
			}
			StartOp(m_Ops.Get(m_OpIndex), now);
			if (m_JobActive)
			{
				return;
			}
		}
	}

	bool GetStrArg(DSBX_QA_Args args, string key, out string value)
	{
		value = "";
		if (!args || !args.sk || !args.sv)
		{
			return false;
		}
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

	bool GetNumArg(DSBX_QA_Args args, string key, out float value)
	{
		value = 0.0;
		if (!args || !args.nk || !args.nv)
		{
			return false;
		}
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

	bool KeyListValid(array<string> keys)
	{
		int i = 0;
		while (i < keys.Count())
		{
			if (keys.Get(i) == "")
			{
				return false;
			}
			int j = i + 1;
			while (j < keys.Count())
			{
				if (keys.Get(j) == keys.Get(i))
				{
					return false;
				}
				j = j + 1;
			}
			i = i + 1;
		}
		return true;
	}

	bool KeyListsDisjoint(array<string> a, array<string> b)
	{
		int i = 0;
		while (i < a.Count())
		{
			int j = 0;
			while (j < b.Count())
			{
				if (a.Get(i) == b.Get(j))
				{
					return false;
				}
				j = j + 1;
			}
			i = i + 1;
		}
		return true;
	}

	bool ValidateGenericArgs(DSBX_QA_Args args)
	{
		if (!args)
		{
			return false;
		}
		if (!args.sk || !args.sv || !args.nk || !args.nv || !args.ncol || !args.ncell || !args.scol || !args.scell)
		{
			return false;
		}
		if (args.sk.Count() != args.sv.Count())
		{
			return false;
		}
		if (args.nk.Count() != args.nv.Count())
		{
			return false;
		}
		if (args.rows < 0)
		{
			return false;
		}
		if (args.ncell.Count() != args.rows * args.ncol.Count())
		{
			return false;
		}
		if (args.scell.Count() != args.rows * args.scol.Count())
		{
			return false;
		}
		if (args.rows > 0 && args.ncol.Count() + args.scol.Count() == 0)
		{
			return false;
		}
		if (!KeyListValid(args.sk))
		{
			return false;
		}
		if (!KeyListValid(args.nk))
		{
			return false;
		}
		if (!KeyListValid(args.ncol))
		{
			return false;
		}
		if (!KeyListValid(args.scol))
		{
			return false;
		}
		if (!KeyListsDisjoint(args.sk, args.nk))
		{
			return false;
		}
		if (!KeyListsDisjoint(args.ncol, args.scol))
		{
			return false;
		}
		int fi = 0;
		while (fi < args.nv.Count())
		{
			if (!IsFiniteF(args.nv.Get(fi)))
			{
				return false;
			}
			fi = fi + 1;
		}
		int ci = 0;
		while (ci < args.ncell.Count())
		{
			if (!IsFiniteF(args.ncell.Get(ci)))
			{
				return false;
			}
			ci = ci + 1;
		}
		string faultRaw;
		if (GetStrArg(args, "qa_fault", faultRaw))
		{
			if (faultRaw.Length() != 24)
			{
				return false;
			}
			string allowed = "abcdefghijklmnopqrstuvwxyz0123456789_ABCDEFGHIJKLMNOPQRSTUVWXYZ";
			int ai = 0;
			while (ai < faultRaw.Length())
			{
				string ch = faultRaw.Substring(ai, 1);
				if (allowed.IndexOf(ch) < 0)
				{
					return false;
				}
				ai = ai + 1;
			}
		}
		return true;
	}

	void StripQaFault(DSBX_QA_Args args)
	{
		m_OpFault = "";
		if (!args || !args.sk || !args.sv)
		{
			return;
		}
		int i = 0;
		while (i < args.sk.Count())
		{
			if (args.sk.Get(i) == "qa_fault")
			{
				string raw = args.sv.Get(i);
				args.sk.RemoveOrdered(i);
				args.sv.RemoveOrdered(i);
				while (raw.Length() > 0 && raw.Substring(raw.Length() - 1, 1) == "_")
				{
					raw = raw.Substring(0, raw.Length() - 1);
				}
				m_OpFault = raw;
				return;
			}
			i = i + 1;
		}
	}

	void HandleJobRead(DSBX_QA_Op op, DSBX_QA_Args args, float recvMs, int frameRecv)
	{
		string jobId;
		float pageF;
		if (!GetStrArg(args, "job", jobId) || !GetNumArg(args, "page_n", pageF) || !IsIntF(pageF))
		{
			FinishInstant(MakeResult(op, "rejected", "bad_args", recvMs, frameRecv));
			return;
		}
		int pageN = (int)pageF;
		DSBX_QA_Job job = m_Jobs.GetJob(jobId);
		if (!job)
		{
			FinishInstant(MakeResult(op, "rejected", "unknown_job", recvMs, frameRecv));
			return;
		}
		int rowsTotal = job.m_RowsTotal;
		int pageSize = job.m_PageSize;
		int pagesN = 0;
		if (rowsTotal > 0)
		{
			pagesN = (rowsTotal + pageSize - 1) / pageSize;
		}
		if (pageN < 0 || (rowsTotal == 0 && pageN > 0) || (rowsTotal > 0 && pageN >= pagesN))
		{
			FinishInstant(MakeResult(op, "rejected", "bad_args", recvMs, frameRecv));
			return;
		}
		int startRow = pageN * pageSize;
		int endRow = startRow + pageSize;
		if (endRow > rowsTotal)
		{
			endRow = rowsTotal;
		}
		DSBX_QA_Result res = MakeResult(op, "done", "", recvMs, frameRecv);
		res.read.has.Insert("payload");
		res.read.sk.Insert("job");
		res.read.sk.Insert("state");
		res.read.sk.Insert("reason");
		res.read.sk.Insert("resource");
		res.read.sv.Insert(job.m_JobId);
		res.read.sv.Insert(job.m_State);
		res.read.sv.Insert(job.m_Reason);
		res.read.sv.Insert(job.m_Resource);
		res.read.nk.Insert("page_n");
		res.read.nk.Insert("pages_n");
		res.read.nk.Insert("rows_total_n");
		res.read.nk.Insert("start_tick_ms");
		res.read.nk.Insert("end_tick_ms");
		res.read.nk.Insert("onjobend_tick_ms");
		res.read.nk.Insert("released_tick_ms");
		res.read.nk.Insert("elapsed_dtsum_ms");
		res.read.nv.Insert(pageN);
		res.read.nv.Insert(pagesN);
		res.read.nv.Insert(rowsTotal);
		res.read.nv.Insert(job.m_StartTickMs);
		res.read.nv.Insert(job.m_EndTickMs);
		res.read.nv.Insert(job.m_OnJobEndTickMs);
		res.read.nv.Insert(job.m_ReleasedTickMs);
		res.read.nv.Insert(job.m_ElapsedDtsumMs);
		int nc = 0;
		while (nc < job.m_Ncol.Count())
		{
			res.read.ncol.Insert(job.m_Ncol.Get(nc));
			nc = nc + 1;
		}
		int sc = 0;
		while (sc < job.m_Scol.Count())
		{
			res.read.scol.Insert(job.m_Scol.Get(sc));
			sc = sc + 1;
		}
		res.read.rows = endRow - startRow;
		int r = startRow;
		while (r < endRow)
		{
			int cc = 0;
			while (cc < job.m_Ncol.Count())
			{
				res.read.ncell.Insert(job.m_Ncell.Get(r * job.m_Ncol.Count() + cc));
				cc = cc + 1;
			}
			int dd = 0;
			while (dd < job.m_Scol.Count())
			{
				res.read.scell.Insert(job.m_Scell.Get(r * job.m_Scol.Count() + dd));
				dd = dd + 1;
			}
			r = r + 1;
		}
		FinishInstant(res);
	}

	void HandleJobStop(DSBX_QA_Op op, DSBX_QA_Args args, float recvMs, int frameRecv)
	{
		string jobId;
		if (!GetStrArg(args, "job", jobId))
		{
			FinishInstant(MakeResult(op, "rejected", "bad_args", recvMs, frameRecv));
			return;
		}
		DSBX_QA_Job job = m_Jobs.GetJob(jobId);
		if (!job)
		{
			FinishInstant(MakeResult(op, "rejected", "unknown_job", recvMs, frameRecv));
			return;
		}
		if (job.m_State == "running")
		{
			m_Jobs.EndJob(jobId, "stopped", "");
			job = m_Jobs.GetJob(jobId);
		}
		DSBX_QA_Result res = MakeResult(op, "done", "", recvMs, frameRecv);
		res.read.has.Insert("payload");
		res.read.sk.Insert("job");
		res.read.sk.Insert("state");
		res.read.sk.Insert("reason");
		res.read.sv.Insert(job.m_JobId);
		res.read.sv.Insert(job.m_State);
		res.read.sv.Insert(job.m_Reason);
		res.read.nk.Insert("rows_total_n");
		res.read.nv.Insert(job.m_RowsTotal);
		FinishInstant(res);
	}

	void HandleJobFree(DSBX_QA_Op op, DSBX_QA_Args args, float recvMs, int frameRecv)
	{
		string jobId;
		if (!GetStrArg(args, "job", jobId))
		{
			FinishInstant(MakeResult(op, "rejected", "bad_args", recvMs, frameRecv));
			return;
		}
		DSBX_QA_Job job = m_Jobs.GetJob(jobId);
		if (!job)
		{
			FinishInstant(MakeResult(op, "rejected", "unknown_job", recvMs, frameRecv));
			return;
		}
		if (job.m_State == "running")
		{
			FinishInstant(MakeResult(op, "rejected", "busy", recvMs, frameRecv));
			return;
		}
		m_Jobs.FreeJob(jobId);
		DSBX_QA_Result res = MakeResult(op, "done", "", recvMs, frameRecv);
		res.read.has.Insert("payload");
		res.read.sk.Insert("job");
		res.read.sk.Insert("freed");
		res.read.sv.Insert(jobId);
		res.read.sv.Insert("1");
		FinishInstant(res);
	}

	void StartOp(DSBX_QA_Op op, float now)
	{
		float recvMs = now;
		int frameRecv = m_Frame;
		m_ResultVerb.Set(op.op_id, op.verb);
		m_OpFault = "";
		if (op.inst != m_Inst)
		{
			FinishInstant(MakeResult(op, "rejected", "stale_instance", recvMs, frameRecv));
			return;
		}
		float restante = op.ttl_ms - (m_BatchNowMs - op.issued_ms);
		float plazo = m_BatchRecvMs + restante;
		if (restante <= 0.0 || now > plazo)
		{
			FinishInstant(MakeResult(op, "rejected", "expired", recvMs, frameRecv));
			return;
		}
		if (m_Cache.Contains(op.op_id))
		{
			DSBX_QA_Result cached = m_Cache.Get(op.op_id);
			DSBX_QA_Result copy = new DSBX_QA_Result();
			copy.op_id = cached.op_id;
			copy.status = cached.status;
			copy.reason = cached.reason;
			copy.dup = 1;
			copy.recv_ms = cached.recv_ms;
			copy.done_ms = cached.done_ms;
			copy.frame_recv = cached.frame_recv;
			copy.frame_done = cached.frame_done;
			copy.read = cached.read;
			m_Bucket.Insert(copy);
			m_OpIndex = m_OpIndex + 1;
			return;
		}
		string verb = op.verb;
		DSBX_QA_Args args = op.args;
		if (!IsF02Verb(verb))
		{
			if (!args || !ValidateGenericArgs(args))
			{
				FinishInstant(MakeResult(op, "rejected", "bad_args", recvMs, frameRecv));
				return;
			}
			StripQaFault(args);
			if (verb == "job_read")
			{
				HandleJobRead(op, args, recvMs, frameRecv);
				return;
			}
			if (verb == "job_stop")
			{
				HandleJobStop(op, args, recvMs, frameRecv);
				return;
			}
			if (verb == "job_free")
			{
				HandleJobFree(op, args, recvMs, frameRecv);
				return;
			}
			int ei = 0;
			while (ei < m_Exts.Count())
			{
				DSBX_QA_Ext ext = m_Exts.Get(ei);
				if (ext.Handles(verb, m_Role))
				{
					DSBX_QA_Result resExt = MakeResult(op, "done", "", recvMs, frameRecv);
					ext.OnStartOp(op, args, resExt);
					resExt.done_ms = NowMs();
					resExt.frame_done = m_Frame;
					FinishInstant(resExt);
					return;
				}
				ei = ei + 1;
			}
			FinishInstant(MakeResult(op, "rejected", "unknown_verb", recvMs, frameRecv));
			return;
		}
		if (!VerbForRole(verb))
		{
			FinishInstant(MakeResult(op, "rejected", "unknown_verb", recvMs, frameRecv));
			return;
		}
		if (!args || !args.pos || args.pos.Count() != 3 || !args.ypr || args.ypr.Count() != 3)
		{
			FinishInstant(MakeResult(op, "rejected", "bad_args", recvMs, frameRecv));
			return;
		}
		if (verb == "ambient_set" && (args.fog < 0.0 || args.fog > 1.0))
		{
			FinishInstant(MakeResult(op, "rejected", "bad_args", recvMs, frameRecv));
			return;
		}
		if (verb == "srv_read")
		{
			DSBX_QA_Result resSrv = MakeResult(op, "done", "", recvMs, frameRecv);
			resSrv.read.has.Insert("frame");
			resSrv.read.has.Insert("tick_s");
			resSrv.read.frame = m_Frame;
			resSrv.read.tick_s = g_Game.GetTickTime();
			FinishInstant(resSrv);
			return;
		}
		if (verb == "ground_query")
		{
			DSBX_QA_Result resGround = MakeResult(op, "done", "", recvMs, frameRecv);
			resGround.read.has.Insert("y");
			resGround.read.y = g_Game.SurfaceY(args.x, args.z);
			FinishInstant(resGround);
			return;
		}
		if (verb == "ambient_read")
		{
			Weather weatherRead = g_Game.GetWeather();
			if (!weatherRead)
			{
				FinishInstant(MakeResult(op, "error", "weather_unavailable", recvMs, frameRecv));
				return;
			}
			DSBX_QA_Result resAmb = MakeResult(op, "done", "", recvMs, frameRecv);
			resAmb.read.has.Insert("fog");
			resAmb.read.fog = weatherRead.GetFog().GetActual();
			FinishInstant(resAmb);
			return;
		}
		if (verb == "cam_pose_read")
		{
			if (!m_Camera)
			{
				FinishInstant(MakeResult(op, "error", "no_camera", recvMs, frameRecv));
				return;
			}
			DSBX_QA_Result resCamRead = MakeResult(op, "done", "", recvMs, frameRecv);
			FillCamRead(resCamRead.read);
			FinishInstant(resCamRead);
			return;
		}
		if (verb == "rpc_log_read")
		{
			DSBX_QA_Result resLog = MakeResult(op, "done", "", recvMs, frameRecv);
			resLog.read.has.Insert("rpc_log");
			int li = 0;
			while (li < m_RpcLog.Count())
			{
				DSBX_QA_RpcEntry src = m_RpcLog.Get(li);
				DSBX_QA_RpcEntry dst = new DSBX_QA_RpcEntry();
				dst.seq = src.seq;
				dst.recv_ms = src.recv_ms;
				dst.lease_age_ms = src.lease_age_ms;
				dst.decision = src.decision;
				resLog.read.rpc_log.Insert(dst);
				li = li + 1;
			}
			FinishInstant(resLog);
			return;
		}
		if (verb == "ambient_set")
		{
			if (!LeaseOk())
			{
				FinishInstant(MakeResult(op, "error", "lease_expired", recvMs, frameRecv));
				return;
			}
			Weather weatherSet = g_Game.GetWeather();
			if (!weatherSet)
			{
				FinishInstant(MakeResult(op, "error", "weather_unavailable", recvMs, frameRecv));
				return;
			}
			if (!m_FogFrozen)
			{
				weatherSet.SetWeatherUpdateFreeze(true);
				m_FogFrozen = true;
			}
			weatherSet.GetFog().Set(args.fog, 0, 0);
			m_JobActive = true;
			m_JobOp = op;
			m_JobArgs = args;
			m_JobRecvMs = recvMs;
			m_JobFrameRecv = frameRecv;
			m_JobStartMs = now;
			m_JobFogTarget = args.fog;
			m_KeepaliveNextMs = now + 500.0;
			return;
		}
		if (verb == "cam_pose_set")
		{
			if (!LeaseOk())
			{
				FinishInstant(MakeResult(op, "error", "lease_expired", recvMs, frameRecv));
				return;
			}
			vector wantPos;
			wantPos[0] = args.pos.Get(0);
			wantPos[1] = args.pos.Get(1);
			wantPos[2] = args.pos.Get(2);
			if (!EnsureCamera(wantPos))
			{
				FinishInstant(MakeResult(op, "error", "camera_create_failed", recvMs, frameRecv));
				return;
			}
			vector wantYpr;
			wantYpr[0] = args.ypr.Get(0);
			wantYpr[1] = args.ypr.Get(1);
			wantYpr[2] = args.ypr.Get(2);
			m_Camera.SetPosition(wantPos);
			m_Camera.SetOrientation(wantYpr);
			m_JobActive = true;
			m_JobOp = op;
			m_JobArgs = args;
			m_JobRecvMs = recvMs;
			m_JobFrameRecv = frameRecv;
			m_JobStartMs = now;
			m_KeepaliveNextMs = now + 500.0;
			return;
		}
		if (verb == "rpc_burst")
		{
			if (args.count <= 0)
			{
				FinishInstant(MakeResult(op, "done", "", recvMs, frameRecv));
				return;
			}
			m_JobActive = true;
			m_JobOp = op;
			m_JobArgs = args;
			m_JobRecvMs = recvMs;
			m_JobFrameRecv = frameRecv;
			m_JobStartMs = now;
			m_BurstIndex = 0;
			m_KeepaliveNextMs = now + 500.0;
			return;
		}
		FinishInstant(MakeResult(op, "rejected", "unknown_verb", recvMs, frameRecv));
	}

	void FillCamRead(DSBX_QA_Read read)
	{
		vector pos = m_Camera.GetPosition();
		vector ypr = m_Camera.GetOrientation();
		read.has.Insert("pos");
		read.has.Insert("ypr");
		read.pos.Set(0, pos[0]);
		read.pos.Set(1, pos[1]);
		read.pos.Set(2, pos[2]);
		read.ypr.Set(0, ypr[0]);
		read.ypr.Set(1, ypr[1]);
		read.ypr.Set(2, ypr[2]);
	}

	bool EnsureCamera(vector pos)
	{
		if (m_Camera)
		{
			return true;
		}
		Object obj = g_Game.CreateObject("staticcamera", pos, true);
		Camera cam = Camera.Cast(obj);
		if (!cam)
		{
			if (obj)
			{
				g_Game.ObjectDelete(obj);
			}
			return false;
		}
		cam.SetActive(true);
		m_Camera = cam;
		return true;
	}

	float AngleDiff(float a, float b)
	{
		float d = a - b;
		while (d > 180.0)
		{
			d = d - 360.0;
		}
		while (d < -180.0)
		{
			d = d + 360.0;
		}
		return AbsF(d);
	}

	void AdvanceJob(float now)
	{
		DSBX_QA_Op op = m_JobOp;
		DSBX_QA_Args args = m_JobArgs;
		string verb = op.verb;
		if (verb == "ambient_set")
		{
			Weather weather = g_Game.GetWeather();
			if (!weather)
			{
				FinishJob(MakeResult(op, "error", "weather_unavailable", m_JobRecvMs, m_JobFrameRecv));
				return;
			}
			float actual = weather.GetFog().GetActual();
			if (AbsF(actual - m_JobFogTarget) <= 0.01 || now - m_JobStartMs >= 1000.0)
			{
				DSBX_QA_Result resAmbSet = MakeResult(op, "done", "", m_JobRecvMs, m_JobFrameRecv);
				resAmbSet.read.has.Insert("fog");
				resAmbSet.read.fog = actual;
				FinishJob(resAmbSet);
			}
			return;
		}
		if (verb == "cam_pose_set")
		{
			if (!m_Camera)
			{
				FinishJob(MakeResult(op, "error", "no_camera", m_JobRecvMs, m_JobFrameRecv));
				return;
			}
			vector posNow = m_Camera.GetPosition();
			vector yprNow = m_Camera.GetOrientation();
			float dx = posNow[0] - args.pos.Get(0);
			float dy = posNow[1] - args.pos.Get(1);
			float dz = posNow[2] - args.pos.Get(2);
			float dist = Math.Sqrt(dx * dx + dy * dy + dz * dz);
			bool anglesOk = true;
			if (AngleDiff(yprNow[0], args.ypr.Get(0)) > 0.5)
			{
				anglesOk = false;
			}
			if (AngleDiff(yprNow[1], args.ypr.Get(1)) > 0.5)
			{
				anglesOk = false;
			}
			if (AngleDiff(yprNow[2], args.ypr.Get(2)) > 0.5)
			{
				anglesOk = false;
			}
			if ((dist <= 0.05 && anglesOk) || now - m_JobStartMs >= 1000.0)
			{
				DSBX_QA_Result resCamSet = MakeResult(op, "done", "", m_JobRecvMs, m_JobFrameRecv);
				FillCamRead(resCamSet.read);
				FinishJob(resCamSet);
			}
			return;
		}
		if (verb == "rpc_burst")
		{
			while (m_BurstIndex < args.count)
			{
				float due = m_JobStartMs + m_BurstIndex * args.interval_ms;
				if (now < due)
				{
					return;
				}
				if (!LeaseOk())
				{
					AddEmitEntry(op.op_id, args.seq0 + m_BurstIndex, "blocked_lease");
					FinishJob(MakeResult(op, "error", "lease_expired", m_JobRecvMs, m_JobFrameRecv));
					return;
				}
				if (!SendCamRpc(args, m_BurstIndex))
				{
					FinishJob(MakeResult(op, "error", "rpc_write_failed", m_JobRecvMs, m_JobFrameRecv));
					return;
				}
				AddEmitEntry(op.op_id, args.seq0 + m_BurstIndex, "sent");
				m_BurstIndex = m_BurstIndex + 1;
			}
			FinishJob(MakeResult(op, "done", "", m_JobRecvMs, m_JobFrameRecv));
			return;
		}
		FinishJob(MakeResult(op, "rejected", "unknown_verb", m_JobRecvMs, m_JobFrameRecv));
	}

	bool SendCamRpc(DSBX_QA_Args args, int i)
	{
		ScriptRPC rpc = new ScriptRPC();
		array<float> posArr = new array<float>();
		posArr.Insert(args.pos.Get(0) + i);
		posArr.Insert(args.pos.Get(1));
		posArr.Insert(args.pos.Get(2));
		array<float> yprArr = new array<float>();
		yprArr.Insert(args.ypr.Get(0));
		yprArr.Insert(args.ypr.Get(1));
		yprArr.Insert(args.ypr.Get(2));
		int seq = args.seq0 + i;
		if (!rpc.Write(seq))
		{
			return false;
		}
		if (!rpc.Write(args.client_inst))
		{
			return false;
		}
		if (!rpc.Write(posArr))
		{
			return false;
		}
		if (!rpc.Write(yprArr))
		{
			return false;
		}
		rpc.Send(null, DSBX_QA_RPC_CAM, true, null);
		return true;
	}

	static void OnAnyRpc(PlayerIdentity sender, Object target, int rpc_type, ParamsReadContext ctx)
	{
		if (rpc_type == DSBX_QA_RPC_CAM)
		{
			if (s_ClientProbe)
			{
				s_ClientProbe.HandleCamRpc(ctx);
			}
			return;
		}
		if (rpc_type >= 26102800 && rpc_type <= 26102889)
		{
			DSBX_QA_Probe probe = s_ClientProbe;
			if (!probe)
			{
				probe = s_ServerProbe;
			}
			if (probe)
			{
				int idx = (rpc_type - 26102800) / 10;
				if (idx >= 0 && idx < probe.m_Exts.Count())
				{
					probe.m_Exts.Get(idx).OnRpc(sender, target, rpc_type, ctx);
				}
			}
			return;
		}
	}

	void HandleCamRpc(ParamsReadContext ctx)
	{
		int seq = 0;
		string targetInst = "";
		array<float> posArr;
		array<float> yprArr;
		if (!ctx.Read(seq))
		{
			return;
		}
		if (!ctx.Read(targetInst))
		{
			return;
		}
		if (!ctx.Read(posArr))
		{
			return;
		}
		if (!ctx.Read(yprArr))
		{
			return;
		}
		if (!posArr || posArr.Count() != 3 || !yprArr || yprArr.Count() != 3)
		{
			return;
		}
		float now = NowMs();
		float leaseAge = 1000000000.0;
		if (m_HasLastOk)
		{
			leaseAge = now - m_LastOkPollMs;
		}
		string decision = "";
		if (targetInst != m_Inst)
		{
			decision = "rejected_inst";
		}
		else if (leaseAge > m_LeaseMs)
		{
			decision = "rejected_lease";
		}
		else if (m_HasSeq && seq <= m_LastSeq)
		{
			decision = "rejected_seq";
		}
		else
		{
			decision = "accepted";
			m_HasSeq = true;
			m_LastSeq = seq;
			m_PendingPos = new array<float>();
			m_PendingPos.Insert(posArr.Get(0));
			m_PendingPos.Insert(posArr.Get(1));
			m_PendingPos.Insert(posArr.Get(2));
			m_PendingYpr = new array<float>();
			m_PendingYpr.Insert(yprArr.Get(0));
			m_PendingYpr.Insert(yprArr.Get(1));
			m_PendingYpr.Insert(yprArr.Get(2));
			m_HasPendingPose = true;
		}
		DSBX_QA_RpcEntry entry = new DSBX_QA_RpcEntry();
		entry.seq = seq;
		entry.recv_ms = now;
		entry.lease_age_ms = leaseAge;
		entry.decision = decision;
		m_RpcLog.Insert(entry);
		while (m_RpcLog.Count() > 512)
		{
			m_RpcLog.RemoveOrdered(0);
		}
	}

	void ApplyPendingPose()
	{
		if (!m_HasPendingPose || !m_IsClient)
		{
			return;
		}
		m_HasPendingPose = false;
		if (!m_PendingPos || !m_PendingYpr)
		{
			return;
		}
		vector pos;
		pos[0] = m_PendingPos.Get(0);
		pos[1] = m_PendingPos.Get(1);
		pos[2] = m_PendingPos.Get(2);
		if (!EnsureCamera(pos))
		{
			return;
		}
		vector ypr;
		ypr[0] = m_PendingYpr.Get(0);
		ypr[1] = m_PendingYpr.Get(1);
		ypr[2] = m_PendingYpr.Get(2);
		m_Camera.SetPosition(pos);
		m_Camera.SetOrientation(ypr);
	}
}


