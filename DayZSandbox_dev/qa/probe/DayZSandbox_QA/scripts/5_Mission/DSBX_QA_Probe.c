const int DSBX_QA_RPC_CAM = 26102701;

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
	const int CALLBACK_POOL_MAX = 4;

	static DSBX_QA_Probe s_ClientProbe;

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
		int uuid[4];
		UUIDApi.Generate(uuid);
		string raw = UUIDApi.FormatString(uuid);
		raw.Replace("-", "");
		raw.ToLower();
		m_Inst = raw;
		if (m_IsClient)
		{
			s_ClientProbe = this;
			DayZGame.Event_OnRPC.Insert(DSBX_QA_Probe.OnCamRpc);
		}
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
		if (m_IsClient)
		{
			DayZGame.Event_OnRPC.Remove(DSBX_QA_Probe.OnCamRpc);
			if (s_ClientProbe == this)
			{
				s_ClientProbe = null;
			}
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
			i++;
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
		string body = "{\"proto\":\"qa0\",\"peer\":\"" + m_Role + "\",\"inst\":\"" + m_Inst + "\",\"build\":\"" + BuildName() + "\",\"probe_ver\":\"dsbx-qa0\"}";
		return body;
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
			i++;
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
		string newUrl = "";
		string newKey = "";
		if (loaded && cfg)
		{
			retry = cfg.retry_ms;
			if (retry <= 0)
			{
				retry = 2000;
			}
			newUrl = cfg.url;
			newKey = cfg.key;
			if (newKey == "")
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
			m_Key = newKey;
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

	DSBX_QA_Callback AcquireCallback(int kind)
	{
		DSBX_QA_Callback cb = null;
		if (kind == KIND_POLL)
		{
			if (!m_PollCallback)
			{
				m_PollCallback = new DSBX_QA_Callback(this);
			}
			cb = m_PollCallback;
		}
		else
		{
			int last = m_CallbackPool.Count() - 1;
			if (last >= 0)
			{
				cb = m_CallbackPool.Get(last);
				m_CallbackPool.Remove(last);
			}
			else
			{
				cb = new DSBX_QA_Callback(this);
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
			i++;
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
		m_State = ST_HELLO;
		m_Ctx.POST(cb, "hello?" + KeyQuery(), HelloBody());
	}

	void SendPoll()
	{
		DSBX_QA_Callback cb = AcquireCallback(KIND_POLL);
		m_State = ST_POLL;
		m_Ctx.GET(cb, "poll?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&frame=" + m_Frame + "&tick_s=" + g_Game.GetTickTime());
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
		if (kind == KIND_RESULT)
		{
			if (success)
			{
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
			if (!parsed)
			{
				RegisterFailure(false, 0);
				return;
			}
			if (resp.lease_ms > 0)
			{
				m_LeaseMs = resp.lease_ms;
			}
			m_FailCount = 0;
			m_HadSuccess = true;
			Log("hello accepted");
			m_State = ST_READY;
			return;
		}
		DSBX_QA_PollResp pollResp = new DSBX_QA_PollResp();
		bool pollParsed = serializer.ReadFromString(pollResp, data, parseErr);
		if (!pollParsed || !pollResp.ops)
		{
			RegisterFailure(false, 0);
			return;
		}
		m_FailCount = 0;
		m_HadSuccess = true;
		m_LastOkPollMs = now;
		m_HasLastOk = true;
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
			i++;
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
		if (kind == KIND_HELLO || kind == KIND_POLL)
		{
			RegisterFailure(true, 0);
		}
	}

	void Tick()
	{
		if (m_ShutdownDone)
		{
			return;
		}
		m_Frame = m_Frame + 1;
		float now = NowMs();
		ApplyPendingPose();
		Watchdog(now);
		if (m_ShutdownDone)
		{
			return;
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
		// Brief v1.3, §4.5: sin string.Replace, que trunca las cadenas largas (3730 -> 1443 B medido en dbg13).
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
		DSBX_QA_Callback cb = AcquireCallback(KIND_RESULT);
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
			m_CacheOrder.Remove(0);
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

	void StartOp(DSBX_QA_Op op, float now)
	{
		float recvMs = now;
		int frameRecv = m_Frame;
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
		if (!VerbForRole(verb))
		{
			FinishInstant(MakeResult(op, "rejected", "unknown_verb", recvMs, frameRecv));
			return;
		}
		DSBX_QA_Args args = op.args;
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
				li++;
			}
			FinishInstant(resLog);
			return;
		}
		if (verb == "ambient_set")
		{
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
			return;
		}
		if (verb == "cam_pose_set")
		{
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
				if (!SendCamRpc(args, m_BurstIndex))
				{
					FinishJob(MakeResult(op, "error", "rpc_write_failed", m_JobRecvMs, m_JobFrameRecv));
					return;
				}
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

	static void OnCamRpc(PlayerIdentity sender, Object target, int rpc_type, ParamsReadContext ctx)
	{
		if (rpc_type != DSBX_QA_RPC_CAM)
		{
			return;
		}
		DSBX_QA_Probe probe = s_ClientProbe;
		if (probe)
		{
			probe.HandleCamRpc(ctx);
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
			m_RpcLog.Remove(0);
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
