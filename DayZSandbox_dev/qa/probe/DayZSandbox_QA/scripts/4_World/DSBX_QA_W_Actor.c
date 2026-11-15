// S3: interfaz de motor de actores (sin dependencia de Expansion) y observador de gestos de EmoteCB/EmoteManager.
// El adaptador de Expansion vive en otro PBO (DayZSandbox_QA_Expansion) y se registra en DSBX_QA_ActorRegistry.

class DSBX_QA_W_Actor : Managed
{
	void DSBX_QA_W_Actor()
	{
	}
}

// Motor de actores: por defecto "no disponible". Un adaptador lo sustituye y lo registra.
class DSBX_QA_ActorBackend : Managed
{
	bool IsAvailable()
	{
		return false;
	}

	// Clase real del actor para un personaje vanilla ("" si no existe).
	string ResolveActorClass(string character)
	{
		return "";
	}

	PlayerBase CreateActor(string actorClass, vector pos)
	{
		return null;
	}

	void ReleaseActor(PlayerBase actor)
	{
	}

	bool SetPassive(PlayerBase actor)
	{
		return false;
	}

	bool SetHostile(PlayerBase actor, string factionKey)
	{
		return false;
	}

	string FactionClass(PlayerBase actor)
	{
		return "";
	}

	bool ClearWaypoints(PlayerBase actor)
	{
		return false;
	}

	bool AddWaypoint(PlayerBase actor, vector pos)
	{
		return false;
	}

	// mode: "HALT", "ONCE" o "LOOP".
	bool SetBehaviour(PlayerBase actor, string mode)
	{
		return false;
	}

	vector CurrentWaypoint(PlayerBase actor)
	{
		return vector.Zero;
	}

	bool TargetPositionIsFinal(PlayerBase actor)
	{
		return false;
	}

	void SetEmote(PlayerBase actor, int emoteId)
	{
	}

	int PendingEmote(PlayerBase actor)
	{
		return 0;
	}
}

class DSBX_QA_ActorRegistry
{
	protected static ref DSBX_QA_ActorBackend s_Backend;
	protected static string s_AdapterStamp;
	protected static float s_CoreStartTickMs;
	protected static float s_AdapterRegTickMs;
	protected static bool s_ForceUnavailable;

	static void MarkCoreStart()
	{
		if (s_CoreStartTickMs <= 0.0 && g_Game)
		{
			s_CoreStartTickMs = g_Game.GetTickTime() * 1000.0;
		}
	}

	static void Register(DSBX_QA_ActorBackend b, string expStamp)
	{
		MarkCoreStart();
		s_Backend = b;
		s_AdapterStamp = expStamp;
		s_ForceUnavailable = false;
		if (g_Game)
		{
			s_AdapterRegTickMs = g_Game.GetTickTime() * 1000.0;
		}
	}

	static DSBX_QA_ActorBackend Get()
	{
		if (!s_Backend)
		{
			s_Backend = new DSBX_QA_ActorBackend();
		}
		return s_Backend;
	}

	static bool IsAvailable()
	{
		if (s_ForceUnavailable)
		{
			return false;
		}
		if (!s_Backend)
		{
			return false;
		}
		return s_Backend.IsAvailable();
	}

	static float GetCoreStartTickMs()
	{
		return s_CoreStartTickMs;
	}

	static float GetAdapterRegTickMs()
	{
		return s_AdapterRegTickMs;
	}

	static string GetAdapterStamp()
	{
		return s_AdapterStamp;
	}

	static string GetBackendClass()
	{
		if (!s_Backend || !s_Backend.IsAvailable())
		{
			return "";
		}
		return s_Backend.Type().ToString();
	}

	// Gancho QA: simula la pérdida de capacidad entre validar y aplicar.
	static void SetForceUnavailable(bool forced)
	{
		s_ForceUnavailable = forced;
	}
}

// Receptor de los eventos de los callbacks de gesto. Lo implementa el monitor de DSBX_QA_X_Actor (5_Mission).
class DSBX_QA_EmoteSink : Managed
{
	void OnBound(PlayerBase player, int cbInstId, int gestureId, int cmdId)
	{
	}

	void OnState(PlayerBase player, int cbInstId, int oldState, int newState)
	{
	}

	void OnFinish(PlayerBase player, int cbInstId, bool canceled)
	{
	}
}

class DSBX_QA_EmoteHub
{
	protected static ref DSBX_QA_EmoteSink s_Sink;

	static void SetSink(DSBX_QA_EmoteSink sink)
	{
		s_Sink = sink;
	}

	static DSBX_QA_EmoteSink GetSink()
	{
		return s_Sink;
	}
}

// Correlación por instancia de callback. EmoteCB no sobrescribe OnFinish en vanilla, así que la causa del fin
// (pCanceled) solo se ve aquí. No copia código de BI: solo avisa y delega en super.
modded class EmoteCB
{
	protected static int s_DsbxNextCbInstId;
	protected int m_DsbxCbInstId;
	protected int m_DsbxBoundReqSeq;

	static int DsbxCbCounter()
	{
		return s_DsbxNextCbInstId;
	}

	int DsbxGetCbInstId()
	{
		return m_DsbxCbInstId;
	}

	// Lo llama EmoteManager.CreateEmoteCallback justo después de fijar m_callbackID, m_player y m_Manager.
	void DsbxOnBound(PlayerBase player, EmoteManager mgr, int gestureId, int cmdId)
	{
		// El linter prohíbe un constructor con el nombre de la clase vanilla en un modded class: la instancia se
		// numera aquí, que es síncrono con la creación (EmoteManager.CreateEmoteCallback).
		if (m_DsbxCbInstId == 0)
		{
			s_DsbxNextCbInstId = s_DsbxNextCbInstId + 1;
			m_DsbxCbInstId = s_DsbxNextCbInstId;
		}
		// [verify] El brief pide EnableStateChangeCallback() en el constructor; aquí, ya con el callback
		// enganchado al comando, para no llamarlo sobre un callback aún sin comando.
		EnableStateChangeCallback();
		DSBX_QA_EmoteSink sink = DSBX_QA_EmoteHub.GetSink();
		if (sink)
		{
			sink.OnBound(player, m_DsbxCbInstId, gestureId, cmdId);
		}
	}

	override void OnStateChange(int pOldState, int pCurrentState)
	{
		super.OnStateChange(pOldState, pCurrentState);
		DSBX_QA_EmoteSink sink = DSBX_QA_EmoteHub.GetSink();
		if (sink)
		{
			sink.OnState(m_player, m_DsbxCbInstId, pOldState, pCurrentState);
		}
	}

	override void OnFinish(bool pCanceled)
	{
		super.OnFinish(pCanceled);
		DSBX_QA_EmoteSink sink = DSBX_QA_EmoteHub.GetSink();
		if (sink)
		{
			sink.OnFinish(m_player, m_DsbxCbInstId, pCanceled);
		}
	}
}

modded class EmoteManager
{
	int DsbxGetCurrentGestureID()
	{
		return m_CurrentGestureID;
	}

	override protected void CreateEmoteCallback(typename callbacktype, int id, int mask, bool fullbody)
	{
		super.CreateEmoteCallback(callbacktype, id, mask, fullbody);
		if (m_Callback)
		{
			m_Callback.DsbxOnBound(m_Player, this, m_CurrentGestureID, id);
		}
	}
}
