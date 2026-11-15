class DSBX_Callback : RestCallback
{
	DSBX_Peer m_Peer;
	int m_Channel;
	int m_Kind;
	int m_Gen;
	bool m_Done;

	void DSBX_Callback(DSBX_Peer peer)
	{
		m_Peer = peer;
		m_Channel = 0;
		m_Kind = 0;
		m_Gen = 0;
		m_Done = true;
	}

	void Arm(DSBX_Peer peer, int channel, int kind, int gen)
	{
		m_Peer = peer;
		m_Channel = channel;
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
		m_Peer = null;
		m_Done = true;
	}

	override void OnSuccess(string data, int dataSize)
	{
		if (m_Done)
		{
			if (m_Peer)
			{
				m_Peer.LogRepeat(m_Channel, m_Kind, "success");
			}
			return;
		}
		m_Done = true;
		DSBX_Peer peer = m_Peer;
		if (peer)
		{
			peer.OnHttpDone(this, m_Channel, m_Kind, m_Gen, true, data, 0, false);
		}
	}

	override void OnError(int errorCode)
	{
		if (m_Done)
		{
			if (m_Peer)
			{
				m_Peer.LogRepeat(m_Channel, m_Kind, "error");
			}
			return;
		}
		m_Done = true;
		DSBX_Peer peer = m_Peer;
		if (peer)
		{
			peer.OnHttpDone(this, m_Channel, m_Kind, m_Gen, false, "", errorCode, false);
		}
	}

	override void OnTimeout()
	{
		if (m_Done)
		{
			if (m_Peer)
			{
				m_Peer.LogRepeat(m_Channel, m_Kind, "timeout");
			}
			return;
		}
		m_Done = true;
		DSBX_Peer peer = m_Peer;
		if (peer)
		{
			peer.OnHttpDone(this, m_Channel, m_Kind, m_Gen, false, "", 0, true);
		}
	}
}

class DSBX_Peer
{
	static DSBX_Peer s_ClientPeer;
	static DSBX_Peer s_ServerPeer;
	static bool s_RestOptionsSet;

	string m_Role;
	bool m_IsClient;
	string m_Inst;
	string m_Epoch;
	string m_Session;
	string m_CatSession;
	string m_HelloEpoch;
	string m_CatSendSession;
	int m_Conn;
	int m_State;

	string m_Key;
	string m_Url;
	RestContext m_Ctx;
	string m_CtxUrl;
	bool m_LogCfgUsable;
	string m_LogCfgReason;

	int m_LeaseMs;
	int m_HoldMs;
	int m_RetryMs;
	int m_KeepaliveMs;
	int m_DeadlineMarginMs;
	int m_RetentionExtraMs;
	int m_CacheCap;
	int m_BaseBackoffMs;
	int m_WatchdogMs;
	float m_NextClockLogMs;
#ifdef DIAG_DEVELOPER
	int m_QaStepGapMs;
	float m_RetirarMs;
#endif
	int m_EpochReqMs;
	int m_CallbackPoolMax;
	int m_CallbackBudget;
	int m_RMaxFailures;
	int m_WireCap;

	float m_NextConfigMs;
	float m_NextEpochReqMs;
	float m_LastOkPollMs;
	bool m_HasLastOkPoll;
	float m_LastPollSendMs;
	float m_KeepaliveNextMs;
	float m_NextTryMsP;
	int m_FailCountP;
	int m_ClientErrCountP;
	bool m_HelloTooLargeLogged;

	int m_NextGen;
	int m_NextKindP;
	int m_NextKindR;
	DSBX_Callback m_ActiveCbP;
	int m_ActiveKindP;
	int m_ActiveGenP;
	float m_ActiveSentMsP;
	DSBX_Callback m_ActiveCbR;
	int m_ActiveKindR;
	int m_ActiveGenR;
	float m_ActiveSentMsR;
	ref array<ref DSBX_Callback> m_PoolP;
	ref array<ref DSBX_Callback> m_PoolR;
	int m_CallbacksCreatedN;
	bool m_BudgetExhausted;
	bool m_BudgetLogged;

	ref DSBX_World m_World;
	ref DSBX_Cache m_Cache;
	ref DSBX_Catalog m_Catalog;
	ref array<ref DSBX_CacheEntry> m_PendingResults;
	DSBX_CacheEntry m_SendingEntry;
	DSBX_CacheEntry m_ActiveEntry;
	string m_GuardFailReason;

	string m_MapName;
	int m_WorldSize;
	ref array<string> m_Modset;

	int m_CatPageIdx;
	int m_CatFailures;
	float m_CatNextTryMs;
	bool m_CatComplete;
	bool m_CatAbandoned;

	bool m_ShutdownDone;

	void DSBX_Peer(string role, DSBX_World world = null)
	{
		m_Role = role;
		m_IsClient = role == "client";
		m_Inst = DSBX_Wire.MakeUuid32();
		m_Epoch = "";
		m_Session = "";
		m_Conn = 0;
		m_State = DSBX_Const.ST_SIN_CONFIG;

		m_Url = "";
		m_Ctx = null;
		m_CtxUrl = "";
		m_LogCfgUsable = false;
		m_LogCfgReason = "";

		m_LeaseMs = DSBX_Const.DEFAULT_LEASE_MS;
		m_HoldMs = DSBX_Const.DEFAULT_HOLD_MS;
		m_RetryMs = DSBX_Const.DEFAULT_RETRY_MS;
		m_KeepaliveMs = DSBX_Const.KEEPALIVE_MS;
		m_DeadlineMarginMs = DSBX_Const.DEADLINE_MARGIN_MS;
		m_RetentionExtraMs = DSBX_Const.RETENTION_EXTRA_MS;
		m_CacheCap = DSBX_Const.CACHE_CAP;
		m_BaseBackoffMs = DSBX_Const.BASE_BACKOFF_MS;
		m_WatchdogMs = DSBX_Const.WATCHDOG_MS;
		m_EpochReqMs = DSBX_Const.EPOCH_REQ_MS;
		m_CallbackPoolMax = DSBX_Const.CALLBACK_POOL_MAX;
		m_CallbackBudget = DSBX_Const.CALLBACK_BUDGET;
		m_RMaxFailures = DSBX_Const.R_MAX_FAILURES;
		m_WireCap = DSBX_WIRE_CAP;

		m_NextConfigMs = 0.0;
		m_NextEpochReqMs = 0.0;
		m_LastOkPollMs = 0.0;
		m_HasLastOkPoll = false;
		m_LastPollSendMs = 0.0;
		m_KeepaliveNextMs = 0.0;
		m_NextTryMsP = 0.0;
		m_FailCountP = 0;
		m_ClientErrCountP = 0;
		m_HelloTooLargeLogged = false;

		m_NextGen = 0;
		m_NextKindP = 0;
		m_NextKindR = 0;
		m_ActiveCbP = null;
		m_ActiveKindP = 0;
		m_ActiveGenP = 0;
		m_ActiveSentMsP = 0.0;
		m_ActiveCbR = null;
		m_ActiveKindR = 0;
		m_ActiveGenR = 0;
		m_ActiveSentMsR = 0.0;
		m_PoolP = new array<ref DSBX_Callback>();
		m_PoolR = new array<ref DSBX_Callback>();
		m_CallbacksCreatedN = 0;
		m_BudgetExhausted = false;
		m_BudgetLogged = false;

		m_World = world;
		m_Cache = new DSBX_Cache(m_CacheCap);
		m_Catalog = null;
		m_PendingResults = new array<ref DSBX_CacheEntry>();
		m_SendingEntry = null;
		m_ActiveEntry = null;
		m_GuardFailReason = "";

		m_MapName = "";
		m_WorldSize = 0;
		m_Modset = new array<string>();

		m_CatPageIdx = 0;
		m_CatFailures = 0;
		m_CatNextTryMs = 0.0;
		m_CatComplete = false;
		m_CatAbandoned = false;
		m_ShutdownDone = false;

		if (!m_IsClient)
		{
			if (!m_World)
			{
				m_World = new DSBX_World();
				m_World.InitServer();
			}
			m_Epoch = m_World.GetEpoch();
			GatherServerEnv();
			m_Catalog = new DSBX_Catalog();
			m_Catalog.StartScan(CatalogBuildName(), m_Modset);
			s_ServerPeer = this;
		}
		else
		{
			s_ClientPeer = this;
		}
		DayZGame.Event_OnRPC.Insert(DSBX_Peer.OnAnyRpc);
	}

	void ~DSBX_Peer()
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
		DayZGame.Event_OnRPC.Remove(DSBX_Peer.OnAnyRpc);
		if (s_ClientPeer == this)
		{
			s_ClientPeer = null;
		}
		if (s_ServerPeer == this)
		{
			s_ServerPeer = null;
		}
		int inflightP = 0;
		int inflightR = 0;
		if (m_ActiveCbP)
		{
			inflightP = 1;
			m_ActiveCbP.Detach();
			m_ActiveCbP = null;
		}
		if (m_ActiveCbR)
		{
			inflightR = 1;
			m_ActiveCbR.Detach();
			m_ActiveCbR = null;
		}
		int i = 0;
		while (i < m_PoolP.Count())
		{
			DSBX_Callback cbP = m_PoolP.Get(i);
			if (cbP)
			{
				cbP.Detach();
			}
			i = i + 1;
		}
		m_PoolP.Clear();
		int j = 0;
		while (j < m_PoolR.Count())
		{
			DSBX_Callback cbR = m_PoolR.Get(j);
			if (cbR)
			{
				cbR.Detach();
			}
			j = j + 1;
		}
		m_PoolR.Clear();
		m_Ctx = null;
		// created_n and the in-flight requests bound the engine's exit report
		// "Leaked 'DSBX_Callback' script instance (Nx)!" (G1 smoke, diag, 15-nov).
		Log("shutdown role=" + m_Role + " created_n=" + m_CallbacksCreatedN + " inflight_p=" + inflightP + " inflight_r=" + inflightR);
	}

	void Log(string msg)
	{
		Print("[DSBX] " + msg);
	}

	float NowMs()
	{
		return g_Game.GetTickTime() * 1000.0;
	}

	string BuildName()
	{
#ifdef DIAG_DEVELOPER
		return "diag";
#else
		return "retail";
#endif
	}

	string CatalogBuildName()
	{
		string ver = "";
		if (g_Game)
		{
			g_Game.GetVersion(ver);
		}
		return BuildName() + " " + ver;
	}

	void GatherServerEnv()
	{
		if (!g_Game)
		{
			return;
		}
		g_Game.GetWorldName(m_MapName);
		if (g_Game.GetWorld())
		{
			m_WorldSize = (int)g_Game.GetWorld().GetWorldSize();
		}
		array<ref ModInfo> infos = new array<ref ModInfo>();
		g_Game.GetModInfos(infos);
		int i = 0;
		while (i < infos.Count())
		{
			ModInfo info = infos.Get(i);
			if (info)
			{
				m_Modset.Insert(info.GetName());
			}
			i = i + 1;
		}
		m_Modset.Sort();
	}

	bool IsKeyChar(int c)
	{
		if (c >= 48 && c <= 57)
		{
			return true;
		}
		if (c >= 65 && c <= 90)
		{
			return true;
		}
		if (c >= 97 && c <= 122)
		{
			return true;
		}
		if (c == 95 || c == 45)
		{
			return true;
		}
		return false;
	}

	bool KeyUsable(string k)
	{
		int n = k.Length();
		if (n < 16 || n > 128)
		{
			return false;
		}
		int i = 0;
		while (i < n)
		{
			int c = k.Substring(i, 1).ToAscii();
			if (!IsKeyChar(c))
			{
				return false;
			}
			i = i + 1;
		}
		return true;
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
		DSBX_PeerConfig cfg;
		string loadErr;
		bool loaded = JsonFileLoader<DSBX_PeerConfig>.LoadFile("$profile:dsbx_peer.json", cfg, loadErr);
		bool usable = false;
		string reason = "missing";
		string newUrl = "";
		if (loaded && cfg)
		{
			newUrl = cfg.url;
			if (cfg.key == "")
			{
				reason = "empty_key";
			}
			else if (!KeyUsable(cfg.key))
			{
				reason = "bad_key_chars";
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
			else
			{
				if (!s_RestOptionsSet)
				{
					api.SetOption(ERestOption.ERESTOPTION_READOPERATION, 3);
					api.SetOption(ERestOption.ERESTOPTION_CONNECTION, 3);
					s_RestOptionsSet = true;
				}
				if (m_CtxUrl != newUrl || !m_Ctx)
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
		}
		if (usable)
		{
			m_Url = newUrl;
			m_Key = cfg.key;
#ifdef DIAG_DEVELOPER
			m_QaStepGapMs = cfg.qa_step_gap_ms;
			if (m_QaStepGapMs < 0)
			{
				m_QaStepGapMs = 0;
			}
			if (m_QaStepGapMs > 10000)
			{
				m_QaStepGapMs = 10000;
			}
			Log("config qa_step_gap_ms=" + m_QaStepGapMs);
#endif
		}
		if (usable != m_LogCfgUsable || reason != m_LogCfgReason)
		{
			m_LogCfgUsable = usable;
			m_LogCfgReason = reason;
			Log("config status=" + reason);
		}
		return usable;
	}

	string KeyQuery()
	{
		return "key=" + m_Key;
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

	DSBX_Callback AcquireCallback(int canal, int kind)
	{
		if (m_BudgetExhausted)
		{
			return null;
		}
		array<ref DSBX_Callback> pool = m_PoolR;
		if (canal == DSBX_Const.CH_P)
		{
			pool = m_PoolP;
		}
		DSBX_Callback cb = null;
		int last = pool.Count() - 1;
		if (last >= 0)
		{
			cb = pool.Get(last);
			pool.RemoveOrdered(last);
		}
		else
		{
			if (m_CallbacksCreatedN >= m_CallbackBudget)
			{
				NoteBudgetReached();
				return null;
			}
			cb = new DSBX_Callback(this);
			m_CallbacksCreatedN = m_CallbacksCreatedN + 1;
		}
		m_NextGen = m_NextGen + 1;
		cb.Arm(this, canal, kind, m_NextGen);
		float now = NowMs();
		if (canal == DSBX_Const.CH_P)
		{
			m_ActiveCbP = cb;
			m_ActiveKindP = kind;
			m_ActiveGenP = m_NextGen;
			m_ActiveSentMsP = now;
		}
		else
		{
			m_ActiveCbR = cb;
			m_ActiveKindR = kind;
			m_ActiveGenR = m_NextGen;
			m_ActiveSentMsR = now;
		}
		return cb;
	}

	void SettleCallback(DSBX_Callback cb, int canal, bool success)
	{
		if (!cb)
		{
			return;
		}
		if (!success)
		{
			cb.Retire();
			return;
		}
		array<ref DSBX_Callback> pool = m_PoolR;
		if (canal == DSBX_Const.CH_P)
		{
			pool = m_PoolP;
		}
		if (pool.Count() < m_CallbackPoolMax)
		{
			pool.Insert(cb);
			return;
		}
		cb.Retire();
	}

	int Send(int canal, string ruta, string body)
	{
		if (!m_Ctx)
		{
			return -1;
		}
		bool isPost = true;
		int kind = m_NextKindR;
		if (canal == DSBX_Const.CH_P)
		{
			kind = m_NextKindP;
			if (kind != DSBX_Const.KIND_HELLO)
			{
				isPost = false;
			}
		}
		if (isPost)
		{
			if (body.Length() > DSBX_WIRE_CAP)
			{
				return -2;
			}
		}
		DSBX_Callback cb = AcquireCallback(canal, kind);
		if (!cb)
		{
			return -1;
		}
		if (isPost)
		{
			m_Ctx.POST(cb, ruta, body);
		}
		else
		{
			m_Ctx.GET(cb, ruta);
		}
		return 0;
	}

	float ComputeBackoffMs(int count)
	{
		float wait = m_BaseBackoffMs;
		int i = 1;
		while (i < count)
		{
			wait = wait * 2.0;
			if (wait > m_RetryMs)
			{
				wait = m_RetryMs;
			}
			i = i + 1;
		}
		if (wait > m_RetryMs)
		{
			wait = m_RetryMs;
		}
		return wait;
	}

	float RetryGapR(int failCount)
	{
		float gap = m_BaseBackoffMs;
		int i = 1;
		while (i < failCount)
		{
			gap = gap * 2.0;
			i = i + 1;
		}
		return gap;
	}

	void OnChannelPError(int errorCode, bool isTimeout)
	{
		if (!isTimeout && errorCode == ERestResultState.EREST_ERROR_CLIENTERROR)
		{
			m_Session = "";
			m_Conn = 0;
			if (m_State != DSBX_Const.ST_HELLO)
			{
				m_State = DSBX_Const.ST_HELLO;
				Log("state HELLO: client error on P");
			}
			m_ClientErrCountP = m_ClientErrCountP + 1;
			m_NextTryMsP = NowMs() + ComputeBackoffMs(m_ClientErrCountP);
			return;
		}
		m_FailCountP = m_FailCountP + 1;
		m_NextTryMsP = NowMs() + ComputeBackoffMs(m_FailCountP);
	}

	void OnChannelRError(int kind, float now)
	{
		if (kind == DSBX_Const.KIND_RESULT)
		{
			if (!m_SendingEntry)
			{
				return;
			}
			m_SendingEntry.m_Attempts = m_SendingEntry.m_Attempts + 1;
			if (m_SendingEntry.m_Attempts >= m_RMaxFailures)
			{
				m_SendingEntry.m_Pending = false;
				m_SendingEntry.m_SendDup = false;
				Log("result abandoned op_id=" + m_SendingEntry.m_Order.op_id);
				m_SendingEntry = null;
				if (m_PendingResults.Count() > 0)
				{
					m_PendingResults.RemoveOrdered(0);
				}
				return;
			}
			m_SendingEntry.m_NextAttemptMs = now + RetryGapR(m_SendingEntry.m_Attempts);
			m_SendingEntry = null;
			return;
		}
		if (kind == DSBX_Const.KIND_CATALOG)
		{
			if (m_CatSendSession != m_CatSession)
			{
				return;
			}
			m_CatFailures = m_CatFailures + 1;
			if (m_CatFailures >= m_RMaxFailures)
			{
				m_CatAbandoned = true;
				Log("catalog abandoned session=" + m_Session);
				return;
			}
			m_CatNextTryMs = now + RetryGapR(m_CatFailures);
		}
	}

	void CheckLeaseTimeout(float now)
	{
		if (m_State != DSBX_Const.ST_LISTO)
		{
			return;
		}
		if (!m_HasLastOkPoll || (now - m_LastOkPollMs) > m_LeaseMs)
		{
			int ageMs = -1;
			if (m_HasLastOkPoll)
			{
				ageMs = (int)(now - m_LastOkPollMs);
			}
			m_Session = "";
			m_Conn = 0;
			m_State = DSBX_Const.ST_HELLO;
			Log("lease lost age_ms=" + ageMs + " tick_ms=" + TickMs());
			Log("lease expired: returning to HELLO");
		}
	}

	void WatchdogP(float now)
	{
		if (!m_ActiveCbP)
		{
			return;
		}
		if ((now - m_ActiveSentMsP) < m_WatchdogMs)
		{
			return;
		}
		DSBX_Callback cb = m_ActiveCbP;
		Log("rest timeout ch=P kind=" + m_ActiveKindP + " src=watchdog tick_ms=" + TickMs());
		m_ActiveCbP = null;
		m_ActiveKindP = 0;
		m_ActiveGenP = 0;
		cb.Retire();
		OnChannelPError(0, true);
	}

	void WatchdogR(float now)
	{
		if (!m_ActiveCbR)
		{
			return;
		}
		if ((now - m_ActiveSentMsR) < m_WatchdogMs)
		{
			return;
		}
		DSBX_Callback cb = m_ActiveCbR;
		int kind = m_ActiveKindR;
		Log("rest timeout ch=R kind=" + kind + " src=watchdog tick_ms=" + TickMs());
		m_ActiveCbR = null;
		m_ActiveKindR = 0;
		m_ActiveGenR = 0;
		cb.Retire();
		OnChannelRError(kind, now);
	}

	void OnHttpDone(DSBX_Callback cb, int canal, int kind, int gen, bool success, string data, int errorCode, bool isTimeout)
	{
		if (m_ShutdownDone)
		{
			return;
		}
		float now = NowMs();
		if (canal == DSBX_Const.CH_P)
		{
			if (cb != m_ActiveCbP || kind != m_ActiveKindP || gen != m_ActiveGenP)
			{
				Log("rest late ch=P kind=" + kind + " tick_ms=" + TickMs());
				return;
			}
			m_ActiveCbP = null;
			m_ActiveKindP = 0;
			m_ActiveGenP = 0;
			SettleCallback(cb, canal, success);
			if (!success)
			{
				LogRestFailure("P", kind, errorCode, isTimeout);
				OnChannelPError(errorCode, isTimeout);
				return;
			}
			HandleChannelPSuccess(kind, data, now);
			return;
		}
		if (canal == DSBX_Const.CH_R)
		{
			if (cb != m_ActiveCbR || kind != m_ActiveKindR || gen != m_ActiveGenR)
			{
				Log("rest late ch=R kind=" + kind + " tick_ms=" + TickMs());
				return;
			}
			m_ActiveCbR = null;
			m_ActiveKindR = 0;
			m_ActiveGenR = 0;
			SettleCallback(cb, canal, success);
			if (!success)
			{
				LogRestFailure("R", kind, errorCode, isTimeout);
				OnChannelRError(kind, now);
				return;
			}
			HandleChannelRSuccess(kind, data, now);
		}
	}

	void HandleChannelPSuccess(int kind, string data, float now)
	{
		JsonSerializer ser = new JsonSerializer();
		string parseErr;
		if (kind == DSBX_Const.KIND_HELLO)
		{
			DSBX_HelloResp resp = new DSBX_HelloResp();
			bool parsed = ser.ReadFromString(resp, data, parseErr);
			if (!parsed || !DSBX_Messages.ValidHello(resp))
			{
				Log("rest invalid ch=P kind=" + kind + " tick_ms=" + TickMs());
				OnChannelPError(0, false);
				return;
			}
			bool isNewSession = m_CatSession != resp.session;
			m_Session = resp.session;
			m_Conn = resp.conn;
			m_LeaseMs = resp.lease_ms;
			m_HoldMs = resp.hold_ms;
			m_WireCap = resp.wire_cap;
			m_LastOkPollMs = now;
			m_HasLastOkPoll = true;
			m_FailCountP = 0;
			m_HelloTooLargeLogged = false;
			if (!m_IsClient && isNewSession)
			{
				m_CatSession = resp.session;
				m_CatPageIdx = 0;
				m_CatFailures = 0;
				m_CatNextTryMs = 0.0;
				m_CatComplete = false;
				m_CatAbandoned = false;
			}
			if (m_IsClient && m_HelloEpoch != m_Epoch)
			{
				m_Session = "";
				m_Conn = 0;
				m_NextTryMsP = 0.0;
				Log("state HELLO: epoch changed during hello");
				return;
			}
			m_State = DSBX_Const.ST_LISTO;
			Log("hello accepted session=" + m_Session + " conn=" + m_Conn);
			return;
		}
		DSBX_PollResp pollResp = new DSBX_PollResp();
		bool pollParsed = ser.ReadFromString(pollResp, data, parseErr);
		if (!pollParsed || !DSBX_Messages.ValidPoll(pollResp))
		{
			Log("rest invalid ch=P kind=" + kind + " tick_ms=" + TickMs());
			OnChannelPError(0, false);
			return;
		}
		m_LastOkPollMs = now;
		m_HasLastOkPoll = true;
		m_FailCountP = 0;
		m_ClientErrCountP = 0;
		if (kind == DSBX_Const.KIND_POLL && pollResp.ops.Count() == 1)
		{
			HandleOrder(pollResp.ops.Get(0), pollResp.now_ms, m_LastPollSendMs, now);
		}
	}

	void HandleChannelRSuccess(int kind, string data, float now)
	{
		JsonSerializer ser = new JsonSerializer();
		string parseErr;
		DSBX_AckResp ackResp = new DSBX_AckResp();
		bool parsed = ser.ReadFromString(ackResp, data, parseErr);
		if (!parsed || !DSBX_Messages.ValidAck(ackResp))
		{
			Log("rest invalid ch=R kind=" + kind + " tick_ms=" + TickMs());
			OnChannelRError(kind, now);
			return;
		}
		if (kind == DSBX_Const.KIND_RESULT)
		{
			if (m_SendingEntry)
			{
				m_SendingEntry.m_Pending = false;
				m_SendingEntry.m_SendDup = false;
				m_SendingEntry.m_Attempts = 0;
				m_SendingEntry.m_NextAttemptMs = 0.0;
				m_SendingEntry = null;
			}
			if (m_PendingResults.Count() > 0)
			{
				m_PendingResults.RemoveOrdered(0);
			}
			return;
		}
		if (kind == DSBX_Const.KIND_CATALOG)
		{
			if (m_CatSendSession != m_CatSession)
			{
				return;
			}
			m_CatFailures = 0;
			m_CatNextTryMs = 0.0;
			m_CatPageIdx = m_CatPageIdx + 1;
			if (m_Catalog && m_CatPageIdx >= m_Catalog.GetPageCount())
			{
				m_CatComplete = true;
				Log("catalog complete pages=" + m_Catalog.GetPageCount());
			}
		}
	}

	void EnqueueResult(DSBX_CacheEntry entry)
	{
		if (!entry)
		{
			return;
		}
		if (!entry.m_Pending)
		{
			entry.m_Pending = true;
			m_PendingResults.Insert(entry);
		}
	}

	void FinishEntry(DSBX_CacheEntry entry, string status, string reason, string readJson)
	{
		if (!entry)
		{
			return;
		}
		entry.m_State = DSBX_Const.CACHE_TERMINADA;
		entry.m_Status = status;
		entry.m_Reason = reason;
		entry.m_ReadJson = readJson;
		entry.m_Attempts = 0;
		entry.m_NextAttemptMs = 0.0;
		entry.m_SendDup = false;
		EnqueueResult(entry);
	}

	void HandleOrder(DSBX_Order order, int pollNowMs, float tSend, float tRecv)
	{
		float now = NowMs();
		int restante = order.ttl_ms - (pollNowMs - order.issued_ms);
		float plazoLocal = tSend + restante - m_DeadlineMarginMs;
		float retencionHasta = tRecv + restante + m_RetentionExtraMs;
		string cacheKey = order.session + "|" + order.op_id;
		DSBX_CacheEntry existing = m_Cache.GetLive(cacheKey, now);
		if (existing)
		{
			if (existing.m_State == DSBX_Const.CACHE_EN_CURSO)
			{
				return;
			}
			if (existing.m_State == DSBX_Const.CACHE_TERMINADA)
			{
				existing.m_SendDup = true;
				existing.m_Attempts = 0;
				existing.m_NextAttemptMs = 0.0;
				EnqueueResult(existing);
				return;
			}
		}
		if (!m_Cache.MakeRoom(now))
		{
			return;
		}
		if (DSBX_Wire.WireId(order.op_id) == "")
		{
			return;
		}
		DSBX_CacheEntry entry = new DSBX_CacheEntry(cacheKey, order, plazoLocal, retencionHasta);
		m_Cache.Put(entry);
		string rejectReason = "";
		if (order.session != m_Session)
		{
			rejectReason = "stale_session";
		}
		else if (order.inst != m_Inst)
		{
			rejectReason = "stale_inst";
		}
		else if (order.conn != m_Conn)
		{
			rejectReason = "stale_conn";
		}
		else if (order.epoch != m_Epoch)
		{
			rejectReason = "stale_epoch";
		}
		else if (now > plazoLocal)
		{
			rejectReason = "expired";
		}
		if (rejectReason != "")
		{
			FinishEntry(entry, "rejected", rejectReason, "{}");
			return;
		}
		StartOrderExecution(entry);
	}

	void StartOrderExecution(DSBX_CacheEntry entry)
	{
		if (m_IsClient || !m_World)
		{
			FinishEntry(entry, "rejected", "unknown_verb", "{}");
			return;
		}
		string verb = entry.m_Order.verb;
		if (verb == "state.read")
		{
			FinishEntry(entry, "done", "", DSBX_Wire.WorldReadJson(m_World));
			return;
		}
		if (verb != "scene.apply")
		{
			FinishEntry(entry, "rejected", "unknown_verb", "{}");
			return;
		}
		if (!entry.m_Order.args || entry.m_Order.args.doc_id == "" || DSBX_Wire.WireId(entry.m_Order.args.hash) == "")
		{
			FinishEntry(entry, "rejected", "bad_args", "{}");
			return;
		}
		m_ActiveEntry = entry;
		m_KeepaliveNextMs = NowMs() + m_KeepaliveMs;
	}

	bool EffectGuard(DSBX_Order order)
	{
		if (!m_ActiveEntry || m_ActiveEntry.m_Order != order)
		{
			m_GuardFailReason = "expired";
			return false;
		}
		float now = NowMs();
		if (!m_HasLastOkPoll || (now - m_LastOkPollMs) > m_LeaseMs)
		{
			m_GuardFailReason = "lease_expired";
			return false;
		}
		if (now > m_ActiveEntry.m_PlazoLocal)
		{
			m_GuardFailReason = "expired";
			return false;
		}
		return true;
	}

	void GuardFailed(DSBX_Order order)
	{
		if (!m_ActiveEntry)
		{
			return;
		}
		DSBX_CacheEntry failedEntry = m_ActiveEntry;
		m_ActiveEntry = null;
		string status = "rejected";
		if (failedEntry.m_StepsDone > 0)
		{
			status = "error";
		}
		FinishEntry(failedEntry, status, m_GuardFailReason, "{}");
	}

	void StepRetirar(DSBX_Order order)
	{
		if (!EffectGuard(order)) { GuardFailed(order); return; }
		m_ActiveEntry.m_StepsDone = 1;
		m_World.SetGeneration(null);
		Log("effect step=retirar session=" + order.session + " op=" + order.op_id + " tick_ms=" + TickMs());
#ifdef DIAG_DEVELOPER
		m_RetirarMs = NowMs();
#endif
	}

	void StepAnotar(DSBX_Order order)
	{
		if (!EffectGuard(order)) { GuardFailed(order); return; }
		m_ActiveEntry.m_StepsDone = 2;
		DSBX_Generation gen = new DSBX_Generation(order.session, order.op_id, order.args.rev, order.args.hash);
		m_World.SetGeneration(gen);
		Log("effect step=anotar session=" + order.session + " op=" + order.op_id + " tick_ms=" + TickMs());
		DSBX_CacheEntry doneEntry = m_ActiveEntry;
		m_ActiveEntry = null;
		FinishEntry(doneEntry, "done", "", DSBX_Wire.WorldReadJson(m_World));
	}

	void AdvanceExecution()
	{
		if (!m_ActiveEntry)
		{
			return;
		}
		if (m_ActiveEntry.m_StepsDone == 0)
		{
			StepRetirar(m_ActiveEntry.m_Order);
			return;
		}
		if (m_ActiveEntry.m_StepsDone == 1)
		{
#ifdef DIAG_DEVELOPER
			if (m_QaStepGapMs > 0 && (NowMs() - m_RetirarMs) < m_QaStepGapMs)
			{
				return;
			}
#endif
			StepAnotar(m_ActiveEntry.m_Order);
		}
	}

	void RequestEpochIfNeeded(float now)
	{
		if (!m_IsClient || m_Epoch != "" || !g_Game)
		{
			return;
		}
		if (now < m_NextEpochReqMs)
		{
			return;
		}
		m_NextEpochReqMs = now + m_EpochReqMs;
		g_Game.RPCSingleParam(null, DSBX_RPC_EPOCH_REQ, new Param1<bool>(true), true, null);
	}

	void SendEpochToIdentity(PlayerIdentity identity)
	{
		if (m_IsClient || !identity || m_Epoch == "" || !g_Game)
		{
			return;
		}
		Param1<string> p = new Param1<string>(m_Epoch);
		g_Game.RPCSingleParam(null, DSBX_RPC_EPOCH, p, true, identity);
	}

	void OnEpochReqRpc(PlayerIdentity sender)
	{
		if (m_IsClient || !sender)
		{
			return;
		}
		SendEpochToIdentity(sender);
	}

	void OnEpochRpc(ParamsReadContext ctx)
	{
		if (!m_IsClient || !ctx)
		{
			return;
		}
		Param1<string> p = new Param1<string>("");
		if (!ctx.Read(p))
		{
			return;
		}
		string newEpoch = p.param1;
		if (!DSBX_Messages.IsHex(newEpoch, 32))
		{
			return;
		}
		if (m_Epoch == newEpoch)
		{
			return;
		}
		bool hadEpoch = m_Epoch != "";
		m_Epoch = newEpoch;
		m_NextConfigMs = 0.0;
		Log("client epoch received");
		if (hadEpoch && m_State == DSBX_Const.ST_LISTO)
		{
			m_Session = "";
			m_Conn = 0;
			m_State = DSBX_Const.ST_HELLO;
			m_NextTryMsP = 0.0;
			Log("state HELLO: epoch changed");
		}
	}

	static void OnAnyRpc(PlayerIdentity sender, Object target, int rpc_type, ParamsReadContext ctx)
	{
		if (rpc_type == DSBX_RPC_EPOCH)
		{
			if (s_ClientPeer)
			{
				s_ClientPeer.OnEpochRpc(ctx);
			}
			return;
		}
		if (rpc_type == DSBX_RPC_EPOCH_REQ)
		{
			if (s_ServerPeer)
			{
				s_ServerPeer.OnEpochReqRpc(sender);
			}
		}
	}

	void TickSinConfig(float now)
	{
		if (m_IsClient && m_Epoch == "")
		{
			RequestEpochIfNeeded(now);
		}
		if (now < m_NextConfigMs)
		{
			return;
		}
		m_NextConfigMs = now + m_RetryMs;
		if (!LoadConfig())
		{
			m_NextConfigMs = now + m_RetryMs;
			return;
		}
		if (m_IsClient && m_Epoch == "")
		{
			return;
		}
		m_State = DSBX_Const.ST_HELLO;
		m_NextTryMsP = 0.0;
		Log("state HELLO");
	}

	void StepHello(float now)
	{
		if (m_ActiveCbP || now < m_NextTryMsP)
		{
			return;
		}
		if (!LoadConfig())
		{
			m_State = DSBX_Const.ST_SIN_CONFIG;
			m_NextConfigMs = now + m_RetryMs;
			Log("state SIN_CONFIG");
			return;
		}
		if (m_IsClient && m_Epoch == "")
		{
			m_State = DSBX_Const.ST_SIN_CONFIG;
			return;
		}
		string body = DSBX_Wire.HelloBody(m_Role, m_Inst, m_Epoch, DSBX_Const.MOD_VER, BuildName(), m_MapName, m_WorldSize, m_Modset);
		m_HelloEpoch = m_Epoch;
		if (body == "")
		{
			m_NextTryMsP = now + m_RetryMs;
			return;
		}
		m_NextKindP = DSBX_Const.KIND_HELLO;
		int rc = Send(DSBX_Const.CH_P, "hello?" + KeyQuery(), body);
		if (rc == -2)
		{
			if (!m_HelloTooLargeLogged)
			{
				m_HelloTooLargeLogged = true;
				Log("hello_too_large bytes=" + body.Length());
			}
			m_NextTryMsP = now + m_RetryMs;
			return;
		}
		if (rc < 0)
		{
			m_NextTryMsP = now + m_RetryMs;
		}
	}

	void StepPoll(float now)
	{
		CheckLeaseTimeout(now);
		if (m_State != DSBX_Const.ST_LISTO)
		{
			return;
		}
		if (m_ActiveCbP || now < m_NextTryMsP)
		{
			return;
		}
		bool needKeepalive = (m_ActiveEntry != null) || (m_SendingEntry != null) || (m_PendingResults.Count() > 0) || m_Cache.HasFullLive(now);
		if (needKeepalive)
		{
			if (now < m_KeepaliveNextMs)
			{
				return;
			}
			m_KeepaliveNextMs = now + m_KeepaliveMs;
			m_LastPollSendMs = now;
			m_NextKindP = DSBX_Const.KIND_KEEPALIVE;
			Send(DSBX_Const.CH_P, "poll?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&session=" + m_Session + "&conn=" + m_Conn + "&deliver=0", "");
			return;
		}
		m_LastPollSendMs = now;
		m_NextKindP = DSBX_Const.KIND_POLL;
		Send(DSBX_Const.CH_P, "poll?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&session=" + m_Session + "&conn=" + m_Conn, "");
	}

	void StepChannelR(float now)
	{
		if (m_ActiveCbR || !m_Ctx || m_Session == "")
		{
			return;
		}
		if (m_PendingResults.Count() > 0)
		{
			DSBX_CacheEntry entry = m_PendingResults.Get(0);
			if (now < entry.m_NextAttemptMs)
			{
				return;
			}
			string body = DSBX_Wire.ResultBody(entry.m_Order.op_id, entry.m_Order.session, entry.m_Order.epoch, entry.m_Status, entry.m_Reason, entry.m_SendDup, entry.m_ReadJson);
			m_NextKindR = DSBX_Const.KIND_RESULT;
			m_SendingEntry = entry;
			int rc = Send(DSBX_Const.CH_R, "result?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&session=" + m_Session, body);
			if (rc == -2)
			{
				entry.m_Status = "error";
				entry.m_Reason = "result_too_large";
				entry.m_ReadJson = "{}";
				string subBody = DSBX_Wire.ResultTooLargeBody(entry.m_Order.op_id, entry.m_Order.session, entry.m_Order.epoch, entry.m_SendDup);
				m_NextKindR = DSBX_Const.KIND_RESULT;
				rc = Send(DSBX_Const.CH_R, "result?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&session=" + m_Session, subBody);
			}
			if (rc != 0)
			{
				OnChannelRError(DSBX_Const.KIND_RESULT, now);
			}
			return;
		}
		if (!m_IsClient && m_Catalog && m_Catalog.IsScanDone() && !m_CatComplete && !m_CatAbandoned)
		{
			if (now < m_CatNextTryMs)
			{
				return;
			}
			if (m_CatPageIdx >= m_Catalog.GetPageCount())
			{
				m_CatComplete = true;
				return;
			}
			string pageBody = m_Catalog.GetPage(m_CatPageIdx);
			m_NextKindR = DSBX_Const.KIND_CATALOG;
			m_CatSendSession = m_CatSession;
			int catRc = Send(DSBX_Const.CH_R, "catalog?" + KeyQuery() + "&peer=" + m_Role + "&inst=" + m_Inst + "&session=" + m_Session, pageBody);
			if (catRc != 0)
			{
				OnChannelRError(DSBX_Const.KIND_CATALOG, now);
			}
		}
	}

	int TickMs()
	{
		return (int)NowMs();
	}

	// El motor invoco otra vez un callback ya cerrado o retirado: se descarta (brief en partida, L-15).
	void LogRepeat(int channel, int kind, string via)
	{
		string ch = "R";
		if (channel == DSBX_Const.CH_P)
		{
			ch = "P";
		}
		Log("rest repeat ch=" + ch + " kind=" + kind + " via=" + via + " tick_ms=" + TickMs());
	}

	// Diagnostico de partida (brief en partida D-P4): R lo registra pero no lo mira (D1).
	void LogRestFailure(string ch, int kind, int errorCode, bool isTimeout)
	{
		if (isTimeout)
		{
			Log("rest timeout ch=" + ch + " kind=" + kind + " src=engine tick_ms=" + TickMs());
			return;
		}
		Log("rest error ch=" + ch + " kind=" + kind + " state=" + errorCode + " tick_ms=" + TickMs());
	}

	void Tick(float timeslice)
	{
		if (m_ShutdownDone)
		{
			return;
		}
		float now = NowMs();
		if (now >= m_NextClockLogMs)
		{
			m_NextClockLogMs = now + 5000.0;
			Log("clock tick_ms=" + TickMs());
		}
		WatchdogP(now);
		WatchdogR(now);
		if (!m_IsClient && m_Catalog && !m_Catalog.IsScanDone())
		{
			if (m_Catalog.TickScan() && m_Catalog.ConsumeScanLogPending())
			{
				Log("catalog scan finished pages=" + m_Catalog.GetPageCount() + " skipped=" + m_Catalog.GetSkippedCount());
			}
		}
		AdvanceExecution();
		StepChannelR(now);
		if (m_State == DSBX_Const.ST_SIN_CONFIG)
		{
			TickSinConfig(now);
			return;
		}
		if (m_State == DSBX_Const.ST_HELLO)
		{
			StepHello(now);
			return;
		}
		if (m_State == DSBX_Const.ST_LISTO)
		{
			StepPoll(now);
		}
	}
}
