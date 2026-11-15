// S3: actores NPC (adaptador de motor por registro), marcas, comportamientos y observador de gestos.
// Verbos act_* solo en el servidor. Las lecturas salen de APIs del motor (posiciones, tick, Σtimeslice,
// callbacks de EmoteCB, inventario, salud); nada se copia de lo pedido ni se calcula como etiqueta.

const string DSBX_QA_ACT_HEAVY_CLASS = "WoodenLog";
const string DSBX_QA_ACT_SEED_CLASS = "Armband_Red";
const string DSBX_QA_ACT_SEED_SLOT = "Armband";
const float DSBX_QA_ACT_ARRIVE_M = 1.5;
const int DSBX_QA_ACT_OBS_MAX_ROWS = 14;

class DSBX_QA_ActorRec : Managed
{
	string m_Id;
	string m_Character;
	string m_Class;
	PlayerBase m_Ent;
	vector m_Pos0;
	string m_InfId;
	Object m_Inf;
	vector m_Inf0;
	float m_ActorHealth0;
	float m_InfHealth0;

	void DSBX_QA_ActorRec()
	{
		m_Id = "";
		m_Character = "";
		m_Class = "";
		m_Ent = null;
		m_Pos0 = vector.Zero;
		m_InfId = "";
		m_Inf = null;
		m_Inf0 = vector.Zero;
		m_ActorHealth0 = 0.0;
		m_InfHealth0 = 0.0;
	}
}

class DSBX_QA_BehRun : Managed
{
	string m_JobId;
	DSBX_QA_ActorRec m_Rec;
	string m_Mode;
	string m_Fault;
	float m_Radius;
	float m_DurationMs;
	float m_ReachTimeoutMs;
	float m_SettleWindowMs;
	float m_StepMs;
	int m_Prng;
	ref array<vector> m_Marks;
	bool m_Started;
	vector m_P0;
	vector m_LastPos;
	float m_DtsumMs;
	float m_NextRowMs;
	int m_Seq;
	float m_StartTick;
	float m_MaxDist;
	float m_PathLen;
	int m_DestReached;
	int m_Legs;
	int m_BuildingsNear;
	int m_TicksChecked;
	int m_OutOfRadius;
	bool m_Reached;
	vector m_Anchor;
	float m_SettleDtsum0;
	float m_SettleTick0;
	float m_SettleMaxDrift;
	string m_MarkState;
	vector m_Wp;
	int m_DestIdx;
	float m_DestTick;
	bool m_HasArrival;
	vector m_LastArrival;
	bool m_DestArrived;
	bool m_RequireThreat;

	void DSBX_QA_BehRun()
	{
		m_JobId = "";
		m_Rec = null;
		m_Mode = "";
		m_Fault = "";
		m_Radius = 15.0;
		m_DurationMs = 0.0;
		m_ReachTimeoutMs = 0.0;
		m_SettleWindowMs = 10000.0;
		m_StepMs = 500.0;
		m_Prng = 1;
		m_Marks = new array<vector>();
		m_Started = false;
		m_P0 = vector.Zero;
		m_LastPos = vector.Zero;
		m_DtsumMs = 0.0;
		m_NextRowMs = 0.0;
		m_Seq = 0;
		m_StartTick = 0.0;
		m_MaxDist = 0.0;
		m_PathLen = 0.0;
		m_DestReached = 0;
		m_Legs = 0;
		m_BuildingsNear = 0;
		m_TicksChecked = 0;
		m_OutOfRadius = 0;
		m_Reached = false;
		m_Anchor = vector.Zero;
		m_SettleDtsum0 = 0.0;
		m_SettleTick0 = 0.0;
		m_SettleMaxDrift = 0.0;
		m_MarkState = "en_ruta";
		m_Wp = vector.Zero;
		m_DestIdx = 0;
		m_DestTick = 0.0;
		m_HasArrival = false;
		m_LastArrival = vector.Zero;
		m_DestArrived = false;
		m_RequireThreat = false;
	}
}

class DSBX_QA_EmoRow : Managed
{
	ref array<float> m_N;
	ref array<string> m_S;

	void DSBX_QA_EmoRow()
	{
		m_N = new array<float>();
		m_S = new array<string>();
	}
}

// Petición de gesto viva de un actor (una por actor). Vive fuera de DSBX_QA_Job: avanza en cada OnTick.
class DSBX_QA_EmoReq : Managed
{
	int m_ReqSeq;
	string m_JobId;
	string m_ActorId;
	PlayerBase m_Actor;
	DSBX_QA_ActorRec m_Rec;
	string m_EmoteKey;
	string m_TestCase;
	string m_Fault;
	string m_Phase;
	int m_ExpEmoteId;
	int m_ExpCmdId;
	int m_PlayEmoteId;
	int m_MaxCbAtReq;
	int m_CbInst;
	int m_ObsEmoteId;
	int m_AnimCmd;
	int m_AnimState;
	int m_OnFinish;
	int m_RawCanceled;
	int m_CancelRequested;
	int m_PostCleanupCb;
	int m_Foreign;
	float m_ReqTick;
	float m_StartTick;
	float m_CancelReqTick;
	float m_EndTick;
	float m_CleanupTick;
	float m_SettleTick;
	string m_State;
	string m_EndCause;
	float m_StartTimeoutMs;
	float m_FinishTimeoutMs;
	float m_StepMs;
	float m_PostWatchMs;
	float m_CombatWaitMs;
	float m_WaitStartTick;
	float m_DtsumMs;
	float m_NextSampleMs;
	int m_RowSeq;
	int m_PeriodicSeq;
	bool m_EvStart;
	bool m_EvFinish;
	bool m_CancelRowDone;
	bool m_CleanupRowDone;
	bool m_Holding;
	EntityAI m_Heavy;
	bool m_ReleaseHold;
	bool m_FirstPeriodicDone;
	float m_CancelTimerMs;
	string m_StopKind;
	float m_RetireTick;
	ref array<ref DSBX_QA_EmoRow> m_Retained;
	ref array<float> m_HistTick;
	ref array<float> m_HistAh;
	ref array<float> m_HistIh;
	ref array<float> m_HistDisp;
	float m_CombatObsTick;

	void DSBX_QA_EmoReq()
	{
		m_ReqSeq = 0;
		m_JobId = "";
		m_ActorId = "";
		m_Actor = null;
		m_Rec = null;
		m_EmoteKey = "";
		m_TestCase = "";
		m_Fault = "";
		m_Phase = "active";
		m_ExpEmoteId = 0;
		m_ExpCmdId = 0;
		m_PlayEmoteId = 0;
		m_MaxCbAtReq = 0;
		m_CbInst = 0;
		m_ObsEmoteId = 0;
		m_AnimCmd = 0;
		m_AnimState = 0;
		m_OnFinish = 0;
		m_RawCanceled = -1;
		m_CancelRequested = 0;
		m_PostCleanupCb = 0;
		m_Foreign = 0;
		m_ReqTick = 0.0;
		m_StartTick = 0.0;
		m_CancelReqTick = 0.0;
		m_EndTick = 0.0;
		m_CleanupTick = 0.0;
		m_SettleTick = 0.0;
		m_State = "pedido";
		m_EndCause = "none";
		m_StartTimeoutMs = 5000.0;
		m_FinishTimeoutMs = 15000.0;
		m_StepMs = 250.0;
		m_PostWatchMs = 0.0;
		m_CombatWaitMs = 5000.0;
		m_WaitStartTick = 0.0;
		m_DtsumMs = 0.0;
		m_NextSampleMs = 0.0;
		m_RowSeq = 0;
		m_PeriodicSeq = 0;
		m_EvStart = false;
		m_EvFinish = false;
		m_CancelRowDone = false;
		m_CleanupRowDone = false;
		m_Holding = false;
		m_Heavy = null;
		m_ReleaseHold = false;
		m_FirstPeriodicDone = false;
		m_CancelTimerMs = 0.0;
		m_StopKind = "";
		m_RetireTick = 0.0;
		m_Retained = new array<ref DSBX_QA_EmoRow>();
		m_HistTick = new array<float>();
		m_HistAh = new array<float>();
		m_HistIh = new array<float>();
		m_HistDisp = new array<float>();
		m_CombatObsTick = 0.0;
	}
}

// Observador de gestos: recibe los eventos de EmoteCB (4_World) y los reenvía al dueño.
class DSBX_QA_ActorEmoteMonitor : DSBX_QA_EmoteSink
{
	DSBX_QA_X_Actor m_Owner;

	void DSBX_QA_ActorEmoteMonitor(DSBX_QA_X_Actor owner)
	{
		m_Owner = owner;
	}

	override void OnBound(PlayerBase player, int cbInstId, int gestureId, int cmdId)
	{
		if (m_Owner)
		{
			m_Owner.EmoOnBound(player, cbInstId, gestureId, cmdId);
		}
	}

	override void OnState(PlayerBase player, int cbInstId, int oldState, int newState)
	{
		if (m_Owner)
		{
			m_Owner.EmoOnState(player, cbInstId, oldState, newState);
		}
	}

	override void OnFinish(PlayerBase player, int cbInstId, bool canceled)
	{
		if (m_Owner)
		{
			m_Owner.EmoOnFinish(player, cbInstId, canceled);
		}
	}
}

class DSBX_QA_X_Actor : DSBX_QA_Ext
{
	ref array<ref DSBX_QA_ActorRec> m_Actors;
	ref array<Object> m_Props;
	ref array<Object> m_Infected;
	ref array<ref DSBX_QA_BehRun> m_BehRuns;
	ref array<ref DSBX_QA_EmoReq> m_Reqs;
	ref DSBX_QA_ActorEmoteMonitor m_Monitor;
	ref array<string> m_BehNcol;
	ref array<string> m_BehScol;
	ref array<string> m_EmoNcol;
	ref array<string> m_EmoScol;
	string m_LastOpId;
	string m_LastOpStatus;
	string m_LastOpReason;
	float m_LoValidate;
	float m_LoCapDrop;
	float m_LoRevalidate;
	float m_LoFirstEffect;
	float m_LoReject;
	int m_LoPropsEver;
	int m_LoActorsEver;
	int m_LoDeletedEver;
	int m_LoEnvEver;
	int m_TotalMut;
	int m_InfSeq;
	int m_ReqCounter;
	float m_PrevTimeMul;
	bool m_InScene;

	void DSBX_QA_X_Actor()
	{
		m_Actors = new array<ref DSBX_QA_ActorRec>();
		m_Props = new array<Object>();
		m_Infected = new array<Object>();
		m_BehRuns = new array<ref DSBX_QA_BehRun>();
		m_Reqs = new array<ref DSBX_QA_EmoReq>();
		m_Monitor = null;
		m_BehNcol = new array<string>();
		m_BehScol = new array<string>();
		m_EmoNcol = new array<string>();
		m_EmoScol = new array<string>();
		m_LastOpId = "";
		m_LastOpStatus = "";
		m_LastOpReason = "";
		m_LoValidate = 0.0;
		m_LoCapDrop = 0.0;
		m_LoRevalidate = 0.0;
		m_LoFirstEffect = -1.0;
		m_LoReject = 0.0;
		m_LoPropsEver = 0;
		m_LoActorsEver = 0;
		m_LoDeletedEver = 0;
		m_LoEnvEver = 0;
		m_TotalMut = 0;
		m_InfSeq = 0;
		m_ReqCounter = 0;
		m_PrevTimeMul = 1.0;
		m_InScene = false;
		string behN = "seq_n frame tick_ms dtsum_ms x_m y_m z_m wp_x_m wp_y_m wp_z_m dist_center_m max_dist_tick_m dist_mark_m settle_dtsum_ms settle_max_drift_m path_len_m dest_reached_n legs_completed_n buildings_near_n ticks_checked_n out_of_radius_ticks_n actor_fighting_b actor_raised_b actor_health inf_health inf_chase_disp_m combat_obs_tick_ms";
		behN.Split(" ", m_BehNcol);
		string behS = "mark_state faction_class infected_id";
		behS.Split(" ", m_BehScol);
		string emoN = "seq_n periodic_seq_n frame tick_ms dtsum_ms req_seq_n cb_inst_id max_cb_inst_at_req_n expected_emote_id observed_emote_id expected_cmd_id anim_cmd_id anim_state_n on_finish_called_b raw_p_canceled_b cancel_requested_b stance_idx hands_empty_b can_play_emote_b em_is_playing_b em_cb_present_b exp_pending_id post_cleanup_cb_count_n foreign_cb_events_n req_tick_ms start_tick_ms cancel_req_tick_ms end_tick_ms cleanup_tick_ms actor_fighting_b actor_raised_b actor_health inf_health inf_chase_disp_m combat_obs_tick_ms";
		emoN.Split(" ", m_EmoNcol);
		string emoS = "emote_key row_kind emote_state observed_end_cause infected_id faction_class";
		emoS.Split(" ", m_EmoScol);
	}

	override void Init(DSBX_QA_Probe probe)
	{
		super.Init(probe);
		if (probe && probe.GetRole() == "server")
		{
			DSBX_QA_ActorRegistry.MarkCoreStart();
			m_Monitor = new DSBX_QA_ActorEmoteMonitor(this);
			DSBX_QA_EmoteHub.SetSink(m_Monitor);
		}
	}

	override bool Handles(string verb, string role)
	{
		if (role != "server")
		{
			return false;
		}
		if (verb == "act_env_freeze" || verb == "act_scene_apply" || verb == "act_reset" || verb == "act_observe")
		{
			return true;
		}
		if (verb == "act_combat_stage" || verb == "act_behaviour_run" || verb == "act_emote_run")
		{
			return true;
		}
		return false;
	}

	// ---------------------------------------------------------------- utilidades de argumentos

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

	int ColIndex(array<string> cols, string name)
	{
		int i = 0;
		while (i < cols.Count())
		{
			if (cols.Get(i) == name)
			{
				return i;
			}
			i = i + 1;
		}
		return -1;
	}

	void Reject(DSBX_QA_Result res, string reason)
	{
		res.status = "rejected";
		res.reason = reason;
	}

	void Fail(DSBX_QA_Result res, string reason)
	{
		res.status = "error";
		res.reason = reason;
	}

	float NowMs()
	{
		return m_Probe.NowMs();
	}

	float Dist2(vector a, vector b)
	{
		float dx = a[0] - b[0];
		float dz = a[2] - b[2];
		return Math.Sqrt(dx * dx + dz * dz);
	}

	float AbsF(float v)
	{
		if (v < 0.0)
		{
			return -v;
		}
		return v;
	}

	void AddNum(DSBX_QA_Read read, string name, float value)
	{
		read.nk.Insert(name);
		read.nv.Insert(value);
	}

	void AddStr(DSBX_QA_Read read, string name, string value)
	{
		read.sk.Insert(name);
		read.sv.Insert(value);
	}

	float BoolF(bool b)
	{
		if (b)
		{
			return 1.0;
		}
		return 0.0;
	}

	string Trunc(string s)
	{
		// E8: ninguna cadena de args/sk/sv/scol de más de 1000 caracteres sale ni se devuelve.
		if (s.Length() > 1000)
		{
			return s.Substring(0, 1000);
		}
		return s;
	}

	DSBX_QA_ActorRec FindActor(string actorId)
	{
		int i = 0;
		while (i < m_Actors.Count())
		{
			DSBX_QA_ActorRec rec = m_Actors.Get(i);
			if (rec && rec.m_Id == actorId && rec.m_Ent)
			{
				return rec;
			}
			i = i + 1;
		}
		return null;
	}

	// Efecto sobre el mundo: cuenta una mutación global y, si es el primero de la orden, anota su tick.
	void NoteEffect()
	{
		m_TotalMut = m_TotalMut + 1;
		// Los contadores last_op_* son de la última act_scene_apply: otros verbos solo suben el global.
		if (m_InScene && m_LoFirstEffect < 0.0)
		{
			m_LoFirstEffect = NowMs();
		}
	}

	void NoteMutation()
	{
		m_TotalMut = m_TotalMut + 1;
	}

	void FillTickFrame(DSBX_QA_Read read)
	{
		AddNum(read, "tick_ms", NowMs());
		AddNum(read, "frame", m_Probe.m_Frame);
	}

	// ---------------------------------------------------------------- despacho

	override void OnStartOp(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string verb = op.verb;
		if (verb == "act_env_freeze")
		{
			DoEnvFreeze(op, args, res);
			return;
		}
		if (verb == "act_scene_apply")
		{
			DoSceneApply(op, args, res);
			return;
		}
		if (verb == "act_reset")
		{
			DoReset(op, args, res);
			return;
		}
		if (verb == "act_observe")
		{
			DoObserve(op, args, res);
			return;
		}
		if (verb == "act_combat_stage")
		{
			DoCombatStage(op, args, res);
			return;
		}
		if (verb == "act_behaviour_run")
		{
			DoBehaviourRun(op, args, res);
			return;
		}
		if (verb == "act_emote_run")
		{
			DoEmoteRun(op, args, res);
			return;
		}
		Reject(res, "unknown_verb");
	}

	// ---------------------------------------------------------------- act_env_freeze

	int EnvWrites(Weather weather, bool setFog, float fogV, bool setOver, float overV, bool setRain, float rainV)
	{
		int writes = 0;
		if (setFog)
		{
			weather.GetFog().Set(fogV, 0, 0);
			writes = writes + 1;
		}
		if (setOver)
		{
			weather.GetOvercast().Set(overV, 0, 0);
			writes = writes + 1;
		}
		if (setRain)
		{
			weather.GetRain().Set(rainV, 0, 0);
			writes = writes + 1;
		}
		return writes;
	}

	bool ValidUnit(float v)
	{
		return m_Probe.IsFiniteF(v) && v >= 0.0 && v <= 1.0;
	}

	void DoEnvFreeze(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		float freezeF;
		if (!GetNum(args, "freeze_b", freezeF) || (freezeF != 0.0 && freezeF != 1.0))
		{
			Reject(res, "bad_args");
			return;
		}
		float hourF;
		float minuteF;
		float fogF;
		float overF;
		float rainF;
		bool hasHour = GetNum(args, "hour_n", hourF);
		bool hasMinute = GetNum(args, "minute_n", minuteF);
		bool hasFog = GetNum(args, "fog", fogF);
		bool hasOver = GetNum(args, "overcast", overF);
		bool hasRain = GetNum(args, "rain", rainF);
		if (hasHour && (!m_Probe.IsIntF(hourF) || hourF < 0.0 || hourF > 23.0))
		{
			Reject(res, "bad_args");
			return;
		}
		if (hasMinute && (!m_Probe.IsIntF(minuteF) || minuteF < 0.0 || minuteF > 59.0))
		{
			Reject(res, "bad_args");
			return;
		}
		if ((hasFog && !ValidUnit(fogF)) || (hasOver && !ValidUnit(overF)) || (hasRain && !ValidUnit(rainF)))
		{
			Reject(res, "bad_args");
			return;
		}
		Weather weather = g_Game.GetWeather();
		if (!weather)
		{
			Fail(res, "weather_unavailable");
			return;
		}
		if (freezeF == 1.0)
		{
			// Escribir ambiente es un efecto operativo: guarda de lease antes de emitir (E1).
			if (!m_Probe.LeaseOk())
			{
				Fail(res, "lease_expired");
				return;
			}
			weather.SetWeatherUpdateFreeze(true);
			g_Game.GetWorld().SetTimeMultiplier(0.0);
			NoteMutation();
			if (hasHour || hasMinute)
			{
				int year;
				int month;
				int day;
				int hour;
				int minute;
				g_Game.GetWorld().GetDate(year, month, day, hour, minute);
				if (hasHour)
				{
					hour = (int)hourF;
				}
				if (hasMinute)
				{
					minute = (int)minuteF;
				}
				g_Game.GetWorld().SetDate(year, month, day, hour, minute);
				NoteMutation();
			}
			int writes = EnvWrites(weather, hasFog, fogF, hasOver, overF, hasRain, rainF);
			m_TotalMut = m_TotalMut + writes;
		}
		else
		{
			// Restaurar es limpieza: corre siempre. [verify] No hay getter del multiplicador previo: se restaura a 1.0.
			weather.SetWeatherUpdateFreeze(false);
			g_Game.GetWorld().SetTimeMultiplier(m_PrevTimeMul);
			NoteMutation();
		}
		res.read.has.Insert("payload");
		FillEnvRead(res.read, weather);
	}

	void FillEnvRead(DSBX_QA_Read read, Weather weather)
	{
		int y;
		int mo;
		int d;
		int h;
		int mi;
		g_Game.GetWorld().GetDate(y, mo, d, h, mi);
		AddNum(read, "weather_frozen_b", BoolF(weather.GetWeatherUpdateFrozen()));
		AddNum(read, "hour_n", h);
		AddNum(read, "minute_n", mi);
		AddNum(read, "fog", weather.GetFog().GetActual());
		AddNum(read, "overcast", weather.GetOvercast().GetActual());
		AddNum(read, "rain", weather.GetRain().GetActual());
		FillTickFrame(read);
	}

	// ---------------------------------------------------------------- act_scene_apply

	string PropClass(int index)
	{
		if (index == 0)
		{
			return "Land_Chair_1";
		}
		return "Barrel_Green";
	}

	vector PropPos(int index)
	{
		// Posiciones del decorado de la fixture s3_actors_preset.json (Chernarus, llano junto al aerodromo).
		if (index == 0)
		{
			return Vector(4522.0, 0.0, 10322.0);
		}
		return Vector(4526.0, 0.0, 10322.0);
	}

	bool ParseWardrobe(string spec, out array<string> slots, out array<string> items)
	{
		slots = new array<string>();
		items = new array<string>();
		if (spec == "")
		{
			return true;
		}
		TStringArray parts = new TStringArray();
		spec.Split(";", parts);
		int i = 0;
		while (i < parts.Count())
		{
			string part = parts.Get(i);
			if (part != "")
			{
				TStringArray kv = new TStringArray();
				part.Split(":", kv);
				if (kv.Count() != 2 || kv.Get(0) == "" || kv.Get(1) == "")
				{
					return false;
				}
				slots.Insert(kv.Get(0));
				items.Insert(kv.Get(1));
			}
			i = i + 1;
		}
		return true;
	}

	bool ItemFitsSlot(string itemClass, string slotName)
	{
		TStringArray slotsOfItem = new TStringArray();
		g_Game.ConfigGetTextArray("CfgVehicles " + itemClass + " inventorySlot", slotsOfItem);
		return slotsOfItem.Find(slotName) >= 0;
	}

	void BeginOp(string opId)
	{
		m_LastOpId = opId;
		m_LastOpStatus = "";
		m_LastOpReason = "";
		m_LoValidate = 0.0;
		m_LoCapDrop = 0.0;
		m_LoRevalidate = 0.0;
		m_LoFirstEffect = -1.0;
		m_LoReject = 0.0;
		m_LoPropsEver = 0;
		m_LoActorsEver = 0;
		m_LoDeletedEver = 0;
		m_LoEnvEver = 0;
	}

	void EndOp(DSBX_QA_Result res)
	{
		m_LastOpStatus = res.status;
		m_LastOpReason = res.reason;
	}

	int SpawnProps(int propsN, array<Object> created)
	{
		int made = 0;
		int i = 0;
		while (i < propsN)
		{
			vector pos = PropPos(i);
			pos[1] = g_Game.SurfaceY(pos[0], pos[2]);
			NoteEffect();
			Object obj = g_Game.CreateObjectEx(PropClass(i), pos, ECE_PLACE_ON_SURFACE | ECE_NOLIFETIME | ECE_NOPERSISTENCY_WORLD);
			m_LoPropsEver = m_LoPropsEver + 1;
			if (obj)
			{
				m_Props.Insert(obj);
				if (created)
				{
					created.Insert(obj);
				}
				made = made + 1;
			}
			i = i + 1;
		}
		return made;
	}

	void DeleteObjectCounted(Object obj)
	{
		if (!obj)
		{
			return;
		}
		g_Game.ObjectDelete(obj);
		NoteMutation();
		m_LoDeletedEver = m_LoDeletedEver + 1;
	}

	void DoSceneApply(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		BeginOp(op.op_id);
		m_InScene = true;
		DoSceneApplyInner(op, args, res);
		m_InScene = false;
		EndOp(res);
	}

	void DoSceneApplyInner(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string capMode;
		float propsF;
		if (!GetStr(args, "cap_mode", capMode) || !GetNum(args, "props_n", propsF))
		{
			Reject(res, "bad_args");
			return;
		}
		if (capMode != "normal" && capMode != "no_expansion" && capMode != "drop_after_validate")
		{
			Reject(res, "bad_args");
			return;
		}
		if (!m_Probe.IsIntF(propsF) || propsF < 0.0 || propsF > 2.0)
		{
			Reject(res, "bad_args");
			return;
		}
		int propsN = (int)propsF;
		string failSlot = "";
		GetStr(args, "fail_slot", failSlot);
		float seedF = 0.0;
		GetNum(args, "seed_pre_gear_b", seedF);
		bool seedPre = seedF == 1.0;
		float hourF;
		float minuteF;
		float fogF;
		float overF;
		float rainF;
		bool hasHour = GetNum(args, "hour_n", hourF);
		bool hasMinute = GetNum(args, "minute_n", minuteF);
		bool hasFog = GetNum(args, "fog", fogF);
		bool hasOver = GetNum(args, "overcast", overF);
		bool hasRain = GetNum(args, "rain", rainF);
		if ((hasHour && (!m_Probe.IsIntF(hourF) || hourF < 0.0 || hourF > 23.0)) || (hasMinute && (!m_Probe.IsIntF(minuteF) || minuteF < 0.0 || minuteF > 59.0)))
		{
			Reject(res, "bad_args");
			return;
		}
		if ((hasFog && !ValidUnit(fogF)) || (hasOver && !ValidUnit(overF)) || (hasRain && !ValidUnit(rainF)))
		{
			Reject(res, "bad_args");
			return;
		}
		int rowsN = args.rows;
		int cId = ColIndex(args.scol, "actor_id");
		int cChar = ColIndex(args.scol, "character");
		int cWard = ColIndex(args.scol, "wardrobe_spec");
		int cX = ColIndex(args.ncol, "x_m");
		int cZ = ColIndex(args.ncol, "z_m");
		if (rowsN > 0 && (cId < 0 || cChar < 0 || cWard < 0 || cX < 0 || cZ < 0))
		{
			Reject(res, "bad_args");
			return;
		}
		array<string> ids = new array<string>();
		array<string> chars = new array<string>();
		array<ref array<string>> wardSlots = new array<ref array<string>>();
		array<ref array<string>> wardItems = new array<ref array<string>>();
		array<float> xs = new array<float>();
		array<float> zs = new array<float>();
		int r = 0;
		while (r < rowsN)
		{
			string aid = args.scell.Get(r * args.scol.Count() + cId);
			string chr = args.scell.Get(r * args.scol.Count() + cChar);
			string spec = args.scell.Get(r * args.scol.Count() + cWard);
			array<string> sl;
			array<string> it;
			if (aid == "" || chr == "" || ids.Find(aid) >= 0 || !ParseWardrobe(spec, sl, it))
			{
				Reject(res, "bad_args");
				return;
			}
			ids.Insert(aid);
			chars.Insert(chr);
			wardSlots.Insert(sl);
			wardItems.Insert(it);
			xs.Insert(args.ncell.Get(r * args.ncol.Count() + cX));
			zs.Insert(args.ncell.Get(r * args.ncol.Count() + cZ));
			r = r + 1;
		}
		// Etapa 1: validate (sin tocar el mundo).
		m_LoValidate = NowMs();
		DSBX_QA_ActorBackend backend = DSBX_QA_ActorRegistry.Get();
		if (rowsN > 0 && (capMode == "no_expansion" || !DSBX_QA_ActorRegistry.IsAvailable()))
		{
			Reject(res, "expansion_unavailable");
			return;
		}
		array<string> classes = new array<string>();
		int a = 0;
		while (a < rowsN)
		{
			string realCls = backend.ResolveActorClass(chars.Get(a));
			if (realCls == "")
			{
				Reject(res, "unknown_class");
				return;
			}
			classes.Insert(realCls);
			array<string> itemsOfA = wardItems.Get(a);
			int w = 0;
			while (w < itemsOfA.Count())
			{
				if (!g_Game.ConfigIsExisting("CfgVehicles " + itemsOfA.Get(w)))
				{
					Reject(res, "unknown_class");
					return;
				}
				w = w + 1;
			}
			a = a + 1;
		}
		int a2 = 0;
		while (a2 < rowsN)
		{
			array<string> slotsOfA = wardSlots.Get(a2);
			array<string> itemsOfA2 = wardItems.Get(a2);
			int w2 = 0;
			while (w2 < slotsOfA.Count())
			{
				if (InventorySlots.GetSlotIdFromString(slotsOfA.Get(w2)) < 0 || !ItemFitsSlot(itemsOfA2.Get(w2), slotsOfA.Get(w2)))
				{
					Reject(res, "incompatible_slot");
					return;
				}
				w2 = w2 + 1;
			}
			if (FindActor(ids.Get(a2)))
			{
				Reject(res, "busy");
				return;
			}
			a2 = a2 + 1;
		}
		string fault = m_Probe.GetOpFault();
		bool earlyProps = fault == "props_before_actor_check" && capMode == "drop_after_validate";
		array<Object> early = new array<Object>();
		float fogPrev = 0.0;
		bool fogTouched = false;
		if (earlyProps)
		{
			// Mutante: aplica decorado y niebla ANTES de comprobar la capacidad, y compensa antes de rechazar.
			if (m_Probe.LeaseOk())
			{
				SpawnProps(propsN, early);
				Weather wEarly = g_Game.GetWeather();
				if (wEarly && hasFog)
				{
					fogPrev = wEarly.GetFog().GetActual();
					wEarly.GetFog().Set(fogF, 0, 0);
					fogTouched = true;
					NoteEffect();
					m_LoEnvEver = m_LoEnvEver + 1;
				}
			}
		}
		// Etapa 2: pre_apply_gate.
		if (capMode == "drop_after_validate")
		{
			m_LoCapDrop = NowMs();
			DSBX_QA_ActorRegistry.SetForceUnavailable(true);
			m_LoRevalidate = NowMs();
			if (rowsN > 0 && !DSBX_QA_ActorRegistry.IsAvailable())
			{
				if (earlyProps)
				{
					int e = 0;
					while (e < early.Count())
					{
						DeleteObjectCounted(early.Get(e));
						e = e + 1;
					}
					if (fogTouched)
					{
						Weather wBack = g_Game.GetWeather();
						if (wBack)
						{
							wBack.GetFog().Set(fogPrev, 0, 0);
							NoteEffect();
							m_LoEnvEver = m_LoEnvEver + 1;
						}
					}
				}
				m_LoReject = NowMs();
				DSBX_QA_ActorRegistry.SetForceUnavailable(false);
				Reject(res, "expansion_unavailable");
				return;
			}
			DSBX_QA_ActorRegistry.SetForceUnavailable(false);
		}
		// Etapa 3: apply_effects. Guarda de lease antes de emitir (E1).
		if (!m_Probe.LeaseOk())
		{
			Fail(res, "lease_expired");
			return;
		}
		int createdProps = 0;
		if (!earlyProps)
		{
			createdProps = SpawnProps(propsN, null);
		}
		else
		{
			createdProps = propsN;
		}
		Weather weather = g_Game.GetWeather();
		if (weather && (hasHour || hasMinute || hasFog || hasOver || hasRain))
		{
			if (hasHour || hasMinute)
			{
				int year;
				int month;
				int day;
				int hour;
				int minute;
				g_Game.GetWorld().GetDate(year, month, day, hour, minute);
				if (hasHour)
				{
					hour = (int)hourF;
				}
				if (hasMinute)
				{
					minute = (int)minuteF;
				}
				NoteEffect();
				g_Game.GetWorld().SetDate(year, month, day, hour, minute);
				m_LoEnvEver = m_LoEnvEver + 1;
			}
			bool fogAgain = hasFog && !earlyProps;
			if (fogAgain || hasOver || hasRain)
			{
				int writes = EnvWrites(weather, fogAgain, fogF, hasOver, overF, hasRain, rainF);
				int wi = 0;
				while (wi < writes)
				{
					NoteEffect();
					wi = wi + 1;
				}
				m_LoEnvEver = m_LoEnvEver + writes;
			}
		}
		int createdActors = 0;
		int seeded = 0;
		int sweepTotal = 0;
		int cleared = 0;
		string applyState = "observado";
		string failedItem = "";
		int k = 0;
		while (k < rowsN)
		{
			vector apos = Vector(xs.Get(k), 0.0, zs.Get(k));
			NoteEffect();
			PlayerBase ent = backend.CreateActor(classes.Get(k), apos);
			m_LoActorsEver = m_LoActorsEver + 1;
			if (!ent)
			{
				Fail(res, "spawn_failed");
				return;
			}
			DSBX_QA_ActorRec rec = new DSBX_QA_ActorRec();
			rec.m_Id = ids.Get(k);
			rec.m_Character = chars.Get(k);
			rec.m_Class = classes.Get(k);
			rec.m_Ent = ent;
			rec.m_Pos0 = ent.GetPosition();
			m_Actors.Insert(rec);
			createdActors = createdActors + 1;
			GameInventory inv = ent.GetInventory();
			if (seedPre)
			{
				int seedSlot = InventorySlots.GetSlotIdFromString(DSBX_QA_ACT_SEED_SLOT);
				if (seedSlot >= 0 && inv.CreateAttachmentEx(DSBX_QA_ACT_SEED_CLASS, seedSlot))
				{
					NoteEffect();
					seeded = seeded + 1;
				}
			}
			// Medido justo antes del barrido: equipo por defecto del actor más los testigos sembrados.
			sweepTotal = sweepTotal + inv.AttachmentCount();
			if (fault != "extra_default_gear")
			{
				cleared = cleared + SweepAttachments(ent);
			}
			array<string> kSlots = wardSlots.Get(k);
			array<string> kItems = wardItems.Get(k);
			int wk = 0;
			while (wk < kSlots.Count())
			{
				bool okItem = false;
				if (kSlots.Get(wk) != failSlot)
				{
					okItem = DressItem(ent, kSlots.Get(wk), kItems.Get(wk));
				}
				if (!okItem && failedItem == "")
				{
					applyState = "parcial";
					failedItem = ids.Get(k) + ":" + kSlots.Get(wk) + ":" + kItems.Get(wk);
				}
				wk = wk + 1;
			}
			k = k + 1;
		}
		res.read.has.Insert("payload");
		AddStr(res.read, "apply_state", applyState);
		AddStr(res.read, "failed_item", Trunc(failedItem));
		AddNum(res.read, "backend_available_b", BoolF(DSBX_QA_ActorRegistry.IsAvailable()));
		AddNum(res.read, "created_props_n", createdProps);
		AddNum(res.read, "created_actors_n", createdActors);
		AddNum(res.read, "pre_gear_seeded_n", seeded);
		AddNum(res.read, "pre_sweep_total_n", sweepTotal);
		AddNum(res.read, "pre_gear_cleared_n", cleared);
		FillTickFrame(res.read);
	}

	// Elimina todos los attachments del actor con la API vanilla de inventario; devuelve cuántos.
	int SweepAttachments(PlayerBase ent)
	{
		GameInventory inv = ent.GetInventory();
		array<EntityAI> found = new array<EntityAI>();
		int n = inv.AttachmentCount();
		int i = 0;
		while (i < n)
		{
			EntityAI att = inv.GetAttachmentFromIndex(i);
			if (att)
			{
				found.Insert(att);
			}
			i = i + 1;
		}
		int removed = 0;
		int j = 0;
		while (j < found.Count())
		{
			EntityAI victim = found.Get(j);
			NoteEffect();
			if (!inv.LocalDestroyEntity(victim))
			{
				g_Game.ObjectDelete(victim);
			}
			removed = removed + 1;
			j = j + 1;
		}
		return removed;
	}

	bool DressItem(PlayerBase ent, string slotName, string itemClass)
	{
		int slotId = InventorySlots.GetSlotIdFromString(slotName);
		if (slotId < 0)
		{
			return false;
		}
		GameInventory inv = ent.GetInventory();
		if (!inv.HasAttachmentSlot(slotId))
		{
			return false;
		}
		NoteEffect();
		EntityAI made = inv.CreateAttachmentEx(itemClass, slotId);
		if (!made)
		{
			return false;
		}
		// Lectura de vuelta: la prenda tiene que estar en esa ranura con esa clase.
		EntityAI back = inv.FindAttachment(slotId);
		if (!back)
		{
			return false;
		}
		string backType = back.GetType();
		return backType == itemClass;
	}

	// ---------------------------------------------------------------- act_reset

	void DoReset(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		// Borra SOLO lo registrado en memoria por la sonda: nunca por radio, clase ni cercanía.
		int delActors = 0;
		int delProps = 0;
		int delInf = 0;
		StopActorJobs("actor_reset");
		DSBX_QA_ActorBackend backend = DSBX_QA_ActorRegistry.Get();
		int i = 0;
		while (i < m_Actors.Count())
		{
			DSBX_QA_ActorRec rec = m_Actors.Get(i);
			if (rec && rec.m_Ent)
			{
				backend.ReleaseActor(rec.m_Ent);
				g_Game.ObjectDelete(rec.m_Ent);
				NoteMutation();
				delActors = delActors + 1;
			}
			i = i + 1;
		}
		m_Actors.Clear();
		int p = 0;
		while (p < m_Props.Count())
		{
			Object prop = m_Props.Get(p);
			if (prop)
			{
				g_Game.ObjectDelete(prop);
				NoteMutation();
				delProps = delProps + 1;
			}
			p = p + 1;
		}
		m_Props.Clear();
		int q = 0;
		while (q < m_Infected.Count())
		{
			Object inf = m_Infected.Get(q);
			if (inf)
			{
				g_Game.ObjectDelete(inf);
				NoteMutation();
				delInf = delInf + 1;
			}
			q = q + 1;
		}
		m_Infected.Clear();
		m_Reqs.Clear();
		res.read.has.Insert("payload");
		AddNum(res.read, "deleted_actors_n", delActors);
		AddNum(res.read, "deleted_props_n", delProps);
		AddNum(res.read, "deleted_infected_n", delInf);
		FillTickFrame(res.read);
	}

	// Termina los trabajos de actor en marcha (el actor desaparece): sus OnJobEnd limpian lo suyo.
	void StopActorJobs(string reason)
	{
		array<string> ids = new array<string>();
		int b = 0;
		while (b < m_BehRuns.Count())
		{
			ids.Insert(m_BehRuns.Get(b).m_JobId);
			b = b + 1;
		}
		int r = 0;
		while (r < m_Reqs.Count())
		{
			DSBX_QA_EmoReq req = m_Reqs.Get(r);
			if (req.m_JobId != "")
			{
				ids.Insert(req.m_JobId);
			}
			r = r + 1;
		}
		int i = 0;
		while (i < ids.Count())
		{
			m_Jobs.EndJob(ids.Get(i), "failed", reason);
			i = i + 1;
		}
		m_BehRuns.Clear();
	}

	// ---------------------------------------------------------------- act_observe

	void DoObserve(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		float cx = 0.0;
		float cz = 0.0;
		float rad = 0.0;
		bool hasC = GetNum(args, "center_x_m", cx) && GetNum(args, "center_z_m", cz) && GetNum(args, "radius_m", rad);
		if (hasC && (!m_Probe.IsFiniteF(cx) || !m_Probe.IsFiniteF(cz) || !m_Probe.IsFiniteF(rad) || rad <= 0.0))
		{
			Reject(res, "bad_args");
			return;
		}
		Weather weather = g_Game.GetWeather();
		if (!weather)
		{
			Fail(res, "weather_unavailable");
			return;
		}
		int propsN = 0;
		int pi = 0;
		while (pi < m_Props.Count())
		{
			Object prop = m_Props.Get(pi);
			if (prop && (!hasC || Dist2(prop.GetPosition(), Vector(cx, 0.0, cz)) <= rad))
			{
				propsN = propsN + 1;
			}
			pi = pi + 1;
		}
		int actorsN = 0;
		int rowsN = 0;
		array<float> ncell = new array<float>();
		array<string> scell = new array<string>();
		int ai = 0;
		while (ai < m_Actors.Count())
		{
			DSBX_QA_ActorRec rec = m_Actors.Get(ai);
			if (rec && rec.m_Ent && rec.m_Ent.IsAlive() && (!hasC || Dist2(rec.m_Ent.GetPosition(), Vector(cx, 0.0, cz)) <= rad))
			{
				actorsN = actorsN + 1;
				GameInventory inv = rec.m_Ent.GetInventory();
				int slotsN = inv.GetAttachmentSlotsCount();
				int si = 0;
				while (si < slotsN)
				{
					int slotId = inv.GetAttachmentSlotId(si);
					EntityAI att = inv.FindAttachment(slotId);
					if (att)
					{
						if (rowsN >= DSBX_QA_ACT_OBS_MAX_ROWS)
						{
							// Cortar filas podría ocultar prendas de más y fabricar un igual: se declara fallo.
							Fail(res, "payload_overflow");
							return;
						}
						scell.Insert(rec.m_Id);
						scell.Insert(rec.m_Ent.GetType());
						scell.Insert(InventorySlots.GetSlotName(slotId));
						scell.Insert(att.GetType());
						vector apos = att.GetPosition();
						ncell.Insert(apos[0]);
						ncell.Insert(apos[1]);
						ncell.Insert(apos[2]);
						ncell.Insert(att.GetHealth01("", ""));
						rowsN = rowsN + 1;
					}
					si = si + 1;
				}
			}
			ai = ai + 1;
		}
		res.read.has.Insert("payload");
		bool avail = DSBX_QA_ActorRegistry.IsAvailable();
		AddStr(res.read, "core_ver", "dsbx-qa1+" + DSBX_QA_STAMP);
		string adapterVer = "";
		if (avail)
		{
			adapterVer = "dsbx-qa-exp1+" + DSBX_QA_ActorRegistry.GetAdapterStamp();
		}
		AddStr(res.read, "adapter_ver", adapterVer);
		AddStr(res.read, "backend_class", DSBX_QA_ActorRegistry.GetBackendClass());
		AddStr(res.read, "last_op_id", m_LastOpId);
		AddStr(res.read, "last_op_status", m_LastOpStatus);
		AddStr(res.read, "last_op_reason", m_LastOpReason);
		AddNum(res.read, "core_loaded_b", 1.0);
		AddNum(res.read, "backend_available_b", BoolF(avail));
		AddNum(res.read, "core_start_tick_ms", DSBX_QA_ActorRegistry.GetCoreStartTickMs());
		AddNum(res.read, "adapter_reg_tick_ms", DSBX_QA_ActorRegistry.GetAdapterRegTickMs());
		int y;
		int mo;
		int d;
		int h;
		int mi;
		g_Game.GetWorld().GetDate(y, mo, d, h, mi);
		AddNum(res.read, "weather_frozen_b", BoolF(weather.GetWeatherUpdateFrozen()));
		AddNum(res.read, "world_props_n", propsN);
		AddNum(res.read, "world_actors_n", actorsN);
		AddNum(res.read, "hour_n", h);
		AddNum(res.read, "minute_n", mi);
		AddNum(res.read, "fog", weather.GetFog().GetActual());
		AddNum(res.read, "overcast", weather.GetOvercast().GetActual());
		AddNum(res.read, "rain", weather.GetRain().GetActual());
		AddNum(res.read, "last_op_validate_tick_ms", m_LoValidate);
		AddNum(res.read, "last_op_cap_drop_tick_ms", m_LoCapDrop);
		AddNum(res.read, "last_op_revalidate_tick_ms", m_LoRevalidate);
		AddNum(res.read, "last_op_first_effect_tick_ms", m_LoFirstEffect);
		AddNum(res.read, "last_op_reject_tick_ms", m_LoReject);
		AddNum(res.read, "last_op_spawned_props_ever_n", m_LoPropsEver);
		AddNum(res.read, "last_op_spawned_actors_ever_n", m_LoActorsEver);
		AddNum(res.read, "last_op_deleted_objects_ever_n", m_LoDeletedEver);
		AddNum(res.read, "last_op_env_writes_ever_n", m_LoEnvEver);
		AddNum(res.read, "total_mutations_seq_n", m_TotalMut);
		FillTickFrame(res.read);
		res.read.ncol.Insert("x_m");
		res.read.ncol.Insert("y_m");
		res.read.ncol.Insert("z_m");
		res.read.ncol.Insert("health_01");
		res.read.scol.Insert("actor_id");
		res.read.scol.Insert("real_class");
		res.read.scol.Insert("slot_name");
		res.read.scol.Insert("item_class");
		int ci = 0;
		while (ci < ncell.Count())
		{
			res.read.ncell.Insert(ncell.Get(ci));
			ci = ci + 1;
		}
		int cj = 0;
		while (cj < scell.Count())
		{
			res.read.scell.Insert(scell.Get(cj));
			cj = cj + 1;
		}
		res.read.rows = rowsN;
	}

	// ---------------------------------------------------------------- act_combat_stage

	float ActorHealth(DSBX_QA_ActorRec rec)
	{
		if (!rec || !rec.m_Ent)
		{
			return 0.0;
		}
		return rec.m_Ent.GetHealth("", "");
	}

	float InfHealth(DSBX_QA_ActorRec rec)
	{
		if (!rec || !rec.m_Inf || !rec.m_Inf.IsAlive())
		{
			return 0.0;
		}
		return rec.m_Inf.GetHealth("", "");
	}

	float InfDisp(DSBX_QA_ActorRec rec)
	{
		if (!rec || !rec.m_Inf)
		{
			return 0.0;
		}
		return Dist2(rec.m_Inf.GetPosition(), rec.m_Inf0);
	}

	void DoCombatStage(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string actorId;
		string factionKey;
		string infClass;
		float distF;
		if (!GetStr(args, "actor_id", actorId) || !GetStr(args, "faction_key", factionKey) || !GetStr(args, "infected_class", infClass) || !GetNum(args, "dist_m", distF))
		{
			Reject(res, "bad_args");
			return;
		}
		if (actorId == "" || factionKey == "" || infClass == "" || !m_Probe.IsFiniteF(distF) || distF <= 0.0)
		{
			Reject(res, "bad_args");
			return;
		}
		DSBX_QA_ActorRec rec = FindActor(actorId);
		if (!rec)
		{
			Reject(res, "unknown_actor");
			return;
		}
		if (!DSBX_QA_ActorRegistry.IsAvailable())
		{
			Reject(res, "expansion_unavailable");
			return;
		}
		if (!g_Game.ConfigIsExisting("CfgVehicles " + infClass))
		{
			Fail(res, "spawn_failed");
			return;
		}
		if (!m_Probe.LeaseOk())
		{
			Fail(res, "lease_expired");
			return;
		}
		DSBX_QA_ActorBackend backend = DSBX_QA_ActorRegistry.Get();
		if (!backend.SetHostile(rec.m_Ent, factionKey))
		{
			Reject(res, "bad_args");
			return;
		}
		vector apos = rec.m_Ent.GetPosition();
		vector ipos = Vector(apos[0] + distF, 0.0, apos[2]);
		ipos[1] = g_Game.SurfaceY(ipos[0], ipos[2]);
		NoteEffect();
		Object inf = g_Game.CreateObjectEx(infClass, ipos, ECE_PLACE_ON_SURFACE | ECE_INITAI | ECE_NOLIFETIME | ECE_NOPERSISTENCY_WORLD);
		if (!inf)
		{
			Fail(res, "spawn_failed");
			return;
		}
		m_Infected.Insert(inf);
		m_InfSeq = m_InfSeq + 1;
		rec.m_InfId = "inf_" + m_InfSeq;
		rec.m_Inf = inf;
		rec.m_Inf0 = inf.GetPosition();
		rec.m_ActorHealth0 = ActorHealth(rec);
		rec.m_InfHealth0 = InfHealth(rec);
		res.read.has.Insert("payload");
		AddStr(res.read, "infected_id", rec.m_InfId);
		AddStr(res.read, "faction_class", backend.FactionClass(rec.m_Ent));
		AddNum(res.read, "init_dist_m", Dist2(rec.m_Ent.GetPosition(), rec.m_Inf0));
		AddNum(res.read, "actor_health_init", rec.m_ActorHealth0);
		AddNum(res.read, "inf_health_init", rec.m_InfHealth0);
		AddNum(res.read, "inf_x0_m", rec.m_Inf0[0]);
		AddNum(res.read, "inf_z0_m", rec.m_Inf0[2]);
		FillTickFrame(res.read);
	}

	// ---------------------------------------------------------------- act_behaviour_run

	int CountBuildings(vector pos)
	{
		array<Object> objs = new array<Object>();
		array<CargoBase> proxies = new array<CargoBase>();
		g_Game.GetObjectsAtPosition(pos, 60.0, objs, proxies);
		int n = 0;
		int i = 0;
		while (i < objs.Count())
		{
			if (Building.Cast(objs.Get(i)))
			{
				n = n + 1;
			}
			i = i + 1;
		}
		return n;
	}

	void DoBehaviourRun(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string actorId;
		string mode;
		float stepF;
		if (!GetStr(args, "actor_id", actorId) || !GetStr(args, "mode", mode) || !GetNum(args, "sample_step_ms", stepF))
		{
			Reject(res, "bad_args");
			return;
		}
		if (actorId == "" || !m_Probe.IsFiniteF(stepF) || stepF <= 0.0)
		{
			Reject(res, "bad_args");
			return;
		}
		if (mode != "ONCE" && mode != "HOLD" && mode != "LOOP" && mode != "ROAM")
		{
			Reject(res, "unknown_mode");
			return;
		}
		string threat = "none";
		GetStr(args, "threat_case", threat);
		if (threat != "none" && threat != "require_threat")
		{
			Reject(res, "bad_args");
			return;
		}
		float durationF = 0.0;
		float reachF = 0.0;
		float settleF = 10000.0;
		float radiusF = 15.0;
		float seedF = 1.0;
		GetNum(args, "duration_ms", durationF);
		GetNum(args, "reach_timeout_ms", reachF);
		GetNum(args, "settle_window_ms", settleF);
		GetNum(args, "radius_m", radiusF);
		GetNum(args, "seed_n", seedF);
		if (!m_Probe.IsFiniteF(durationF) || !m_Probe.IsFiniteF(reachF) || !m_Probe.IsFiniteF(settleF) || !m_Probe.IsFiniteF(radiusF) || !m_Probe.IsFiniteF(seedF) || radiusF <= 0.0 || settleF <= 0.0 || seedF < 0.0)
		{
			Reject(res, "bad_args");
			return;
		}
		if (mode == "ONCE" && (reachF <= 0.0 || args.rows != 1))
		{
			Reject(res, "bad_args");
			return;
		}
		if (mode == "LOOP" && (durationF <= 0.0 || args.rows < 2))
		{
			Reject(res, "bad_args");
			return;
		}
		if ((mode == "HOLD" || mode == "ROAM") && durationF <= 0.0)
		{
			Reject(res, "bad_args");
			return;
		}
		int cX = ColIndex(args.ncol, "wp_x_m");
		int cY = ColIndex(args.ncol, "wp_y_m");
		int cZ = ColIndex(args.ncol, "wp_z_m");
		if (args.rows > 0 && (cX < 0 || cZ < 0))
		{
			Reject(res, "bad_args");
			return;
		}
		DSBX_QA_ActorRec rec = FindActor(actorId);
		if (!rec)
		{
			Reject(res, "unknown_actor");
			return;
		}
		if (!DSBX_QA_ActorRegistry.IsAvailable())
		{
			Reject(res, "expansion_unavailable");
			return;
		}
		if (!m_Probe.LeaseOk())
		{
			Fail(res, "lease_expired");
			return;
		}
		float maxDur = durationF + 60000.0;
		if (mode == "ONCE")
		{
			maxDur = reachF + settleF + 30000.0;
		}
		string err = m_Jobs.StartJob(this, op.op_id, "actor:" + actorId, m_BehNcol, m_BehScol, 4, 4096, maxDur, "stop");
		if (err != "")
		{
			Reject(res, err);
			return;
		}
		DSBX_QA_BehRun run = new DSBX_QA_BehRun();
		run.m_JobId = op.op_id;
		run.m_Rec = rec;
		run.m_Mode = mode;
		run.m_Fault = m_Probe.GetOpFault();
		run.m_Radius = radiusF;
		run.m_DurationMs = durationF;
		run.m_ReachTimeoutMs = reachF;
		run.m_SettleWindowMs = settleF;
		run.m_StepMs = stepF;
		run.m_Prng = ((int)seedF * 7919 + 13) % 65537;
		run.m_RequireThreat = threat == "require_threat";
		int r = 0;
		while (r < args.rows)
		{
			float wx = args.ncell.Get(r * args.ncol.Count() + cX);
			float wy = 0.0;
			if (cY >= 0)
			{
				wy = args.ncell.Get(r * args.ncol.Count() + cY);
			}
			float wz = args.ncell.Get(r * args.ncol.Count() + cZ);
			run.m_Marks.Insert(Vector(wx, wy, wz));
			r = r + 1;
		}
		DSBX_QA_Job job = m_Jobs.GetJob(op.op_id);
		if (job)
		{
			run.m_StartTick = job.m_StartTickMs;
		}
		else
		{
			run.m_StartTick = NowMs();
		}
		m_BehRuns.Insert(run);
		m_Jobs.FillStartRead(res.read, op.op_id, "actor:" + actorId);
	}

	float NextRnd(DSBX_QA_BehRun run)
	{
		run.m_Prng = (run.m_Prng * 75 + 74) % 65537;
		return run.m_Prng / 65537.0;
	}

	// Siguiente destino de ROAM: anillo [0.35 r, 0.75 r] alrededor de P0 (el 3.º, 22 m con el mutante).
	vector NextRoamDest(DSBX_QA_BehRun run)
	{
		float ang = Math.PI2 * NextRnd(run);
		float frac = 0.35 + 0.4 * NextRnd(run);
		float dist = run.m_Radius * frac;
		if (run.m_Fault == "roam_ignore_radius" && run.m_DestIdx == 2)
		{
			dist = 22.0;
		}
		vector dest = Vector(run.m_P0[0] + Math.Cos(ang) * dist, 0.0, run.m_P0[2] + Math.Sin(ang) * dist);
		dest[1] = g_Game.SurfaceY(dest[0], dest[2]);
		return dest;
	}

	void SendRoamDest(DSBX_QA_BehRun run, float now)
	{
		DSBX_QA_ActorBackend backend = DSBX_QA_ActorRegistry.Get();
		run.m_Wp = NextRoamDest(run);
		run.m_DestIdx = run.m_DestIdx + 1;
		run.m_DestTick = now;
		run.m_DestArrived = false;
		backend.ClearWaypoints(run.m_Rec.m_Ent);
		backend.AddWaypoint(run.m_Rec.m_Ent, run.m_Wp);
		backend.SetBehaviour(run.m_Rec.m_Ent, "ONCE");
	}

	bool AppendBehRow(DSBX_QA_BehRun run, vector pos, float now)
	{
		DSBX_QA_ActorRec rec = run.m_Rec;
		PlayerBase ent = rec.m_Ent;
		DSBX_QA_ActorBackend backend = DSBX_QA_ActorRegistry.Get();
		array<float> n = new array<float>();
		n.Insert(run.m_Seq);
		n.Insert(m_Probe.m_Frame);
		n.Insert(now);
		n.Insert(run.m_DtsumMs);
		n.Insert(pos[0]);
		n.Insert(pos[1]);
		n.Insert(pos[2]);
		n.Insert(run.m_Wp[0]);
		n.Insert(run.m_Wp[1]);
		n.Insert(run.m_Wp[2]);
		n.Insert(Dist2(pos, run.m_P0));
		n.Insert(run.m_MaxDist);
		n.Insert(Dist2(pos, run.m_Wp));
		float settleDt = 0.0;
		if (run.m_Reached)
		{
			settleDt = run.m_DtsumMs - run.m_SettleDtsum0;
		}
		n.Insert(settleDt);
		n.Insert(run.m_SettleMaxDrift);
		n.Insert(run.m_PathLen);
		n.Insert(run.m_DestReached);
		n.Insert(run.m_Legs);
		n.Insert(run.m_BuildingsNear);
		n.Insert(run.m_TicksChecked);
		n.Insert(run.m_OutOfRadius);
		n.Insert(BoolF(ent.IsFighting()));
		n.Insert(BoolF(ent.IsRaised()));
		n.Insert(ActorHealth(rec));
		n.Insert(InfHealth(rec));
		n.Insert(InfDisp(rec));
		n.Insert(now);
		array<string> s = new array<string>();
		s.Insert(run.m_MarkState);
		s.Insert(backend.FactionClass(ent));
		s.Insert(rec.m_InfId);
		run.m_Seq = run.m_Seq + 1;
		return m_Jobs.AppendRow(run.m_JobId, n, s);
	}

	void StopActorMotion(PlayerBase ent)
	{
		if (!ent)
		{
			return;
		}
		DSBX_QA_ActorBackend backend = DSBX_QA_ActorRegistry.Get();
		backend.ClearWaypoints(ent);
		backend.SetBehaviour(ent, "HALT");
	}

	void TickBehaviour(DSBX_QA_BehRun run, float timeslice)
	{
		if (m_Jobs.GetState(run.m_JobId) != "running")
		{
			return;
		}
		// Hombre muerto (E1): ninguna emisión con el lease caducado.
		if (m_Jobs.IsDeadmanTripped(run.m_JobId))
		{
			m_Jobs.EndJob(run.m_JobId, "failed", "lease_expired");
			return;
		}
		PlayerBase ent = null;
		if (run.m_Rec)
		{
			ent = run.m_Rec.m_Ent;
		}
		if (!ent)
		{
			m_Jobs.EndJob(run.m_JobId, "failed", "actor_lost");
			return;
		}
		DSBX_QA_ActorBackend backend = DSBX_QA_ActorRegistry.Get();
		float now = NowMs();
		vector pos = ent.GetPosition();
		bool first = !run.m_Started;
		bool forceRow = false;
		bool finalRow = false;
		if (first)
		{
			run.m_Started = true;
			run.m_P0 = pos;
			run.m_LastPos = pos;
			run.m_BuildingsNear = CountBuildings(pos);
			run.m_NextRowMs = run.m_StepMs;
			run.m_Wp = pos;
			if (run.m_Mode == "ONCE")
			{
				run.m_Wp = run.m_Marks.Get(0);
			}
			if (run.m_Mode == "LOOP")
			{
				run.m_Wp = run.m_Marks.Get(0);
			}
			forceRow = true;
		}
		else
		{
			run.m_DtsumMs = run.m_DtsumMs + timeslice * 1000.0;
		}
		// Mediciones por tick del servidor.
		run.m_PathLen = run.m_PathLen + Dist2(pos, run.m_LastPos);
		run.m_LastPos = pos;
		float dCenter = Dist2(pos, run.m_P0);
		if (dCenter > run.m_MaxDist)
		{
			run.m_MaxDist = dCenter;
		}
		run.m_TicksChecked = run.m_TicksChecked + 1;
		if (run.m_Mode == "ROAM" && dCenter > run.m_Radius)
		{
			run.m_OutOfRadius = run.m_OutOfRadius + 1;
		}
		if (!first)
		{
			if (run.m_Mode == "ONCE")
			{
				finalRow = TickOnce(run, ent, backend, pos, now, timeslice);
				if (run.m_Reached && run.m_Legs == 0)
				{
					run.m_Legs = 1;
					forceRow = true;
				}
			}
			if (run.m_Mode == "HOLD")
			{
				if (run.m_DtsumMs >= run.m_DurationMs)
				{
					finalRow = true;
				}
			}
			if (run.m_Mode == "LOOP")
			{
				vector cur = backend.CurrentWaypoint(ent);
				if (cur != vector.Zero)
				{
					run.m_Wp = cur;
				}
				if (Dist2(pos, run.m_Wp) < DSBX_QA_ACT_ARRIVE_M)
				{
					if (!run.m_HasArrival || Dist2(run.m_LastArrival, run.m_Wp) > 0.5)
					{
						run.m_Legs = run.m_Legs + 1;
						run.m_HasArrival = true;
						run.m_LastArrival = run.m_Wp;
					}
				}
				if (run.m_DtsumMs >= run.m_DurationMs)
				{
					finalRow = true;
				}
			}
			if (run.m_Mode == "ROAM")
			{
				if (run.m_Fault != "roam_stand_still")
				{
					if (!run.m_DestArrived && Dist2(pos, run.m_Wp) < DSBX_QA_ACT_ARRIVE_M)
					{
						run.m_DestArrived = true;
						run.m_DestReached = run.m_DestReached + 1;
					}
					if (run.m_DestArrived || now - run.m_DestTick >= 90000.0)
					{
						SendRoamDest(run, now);
					}
				}
				if (run.m_DtsumMs >= run.m_DurationMs)
				{
					finalRow = true;
				}
			}
		}
		else
		{
			// Primera muestra con el actor aún donde lo dejó la escena; las órdenes salen después.
			if (run.m_Mode == "ONCE")
			{
				backend.ClearWaypoints(ent);
				backend.AddWaypoint(ent, run.m_Marks.Get(0));
				backend.SetBehaviour(ent, "ONCE");
			}
			if (run.m_Mode == "HOLD")
			{
				backend.ClearWaypoints(ent);
				backend.SetBehaviour(ent, "HALT");
			}
			if (run.m_Mode == "LOOP")
			{
				backend.ClearWaypoints(ent);
				int m = 0;
				while (m < run.m_Marks.Count())
				{
					backend.AddWaypoint(ent, run.m_Marks.Get(m));
					m = m + 1;
				}
				backend.SetBehaviour(ent, "LOOP");
			}
			if (run.m_Mode == "ROAM")
			{
				if (run.m_Fault == "roam_stand_still")
				{
					backend.ClearWaypoints(ent);
					backend.SetBehaviour(ent, "HALT");
				}
				else
				{
					SendRoamDest(run, now);
				}
			}
		}
		bool due = run.m_DtsumMs >= run.m_NextRowMs;
		if (forceRow || due || finalRow)
		{
			if (due)
			{
				run.m_NextRowMs = run.m_NextRowMs + run.m_StepMs;
				if (run.m_NextRowMs <= run.m_DtsumMs)
				{
					run.m_NextRowMs = run.m_DtsumMs + run.m_StepMs;
				}
			}
			AppendBehRow(run, pos, now);
		}
		if (finalRow)
		{
			m_Jobs.EndJob(run.m_JobId, "done", "");
		}
	}

	// Lógica de ONCE: llegada por geometría (< 1.5 m), ventana de asentamiento y plazo. Devuelve true al cerrar.
	bool TickOnce(DSBX_QA_BehRun run, PlayerBase ent, DSBX_QA_ActorBackend backend, vector pos, float now, float timeslice)
	{
		run.m_Wp = run.m_Marks.Get(0);
		if (!run.m_Reached)
		{
			bool arrived = Dist2(pos, run.m_Wp) < DSBX_QA_ACT_ARRIVE_M;
			// Mutante: toma como llegada el isFinal del FSM aunque la marca no esté a menos de 1.5 m.
			if (run.m_Fault == "fsm_is_final_as_reached" && backend.TargetPositionIsFinal(ent))
			{
				arrived = true;
			}
			if (arrived)
			{
				run.m_Reached = true;
				run.m_MarkState = "en_marca";
				run.m_Anchor = pos;
				run.m_SettleDtsum0 = run.m_DtsumMs;
				run.m_SettleTick0 = now;
				run.m_SettleMaxDrift = 0.0;
				return false;
			}
			if (now - run.m_StartTick + timeslice * 1000.0 >= run.m_ReachTimeoutMs)
			{
				run.m_MarkState = "agotado";
				return true;
			}
			return false;
		}
		float drift = Dist2(pos, run.m_Anchor);
		if (drift > run.m_SettleMaxDrift)
		{
			run.m_SettleMaxDrift = drift;
		}
		if (run.m_DtsumMs - run.m_SettleDtsum0 >= run.m_SettleWindowMs && now - run.m_SettleTick0 >= run.m_SettleWindowMs)
		{
			return true;
		}
		return false;
	}

	// ---------------------------------------------------------------- act_emote_run: tablas y arranque

	int EmoteIdByKey(string key)
	{
		if (key == "nod")
		{
			return EmoteConstants.ID_EMOTE_NOD;
		}
		if (key == "shake")
		{
			return EmoteConstants.ID_EMOTE_SHAKE;
		}
		if (key == "shrug")
		{
			return EmoteConstants.ID_EMOTE_SHRUG;
		}
		if (key == "clap")
		{
			return EmoteConstants.ID_EMOTE_CLAP;
		}
		if (key == "move")
		{
			return EmoteConstants.ID_EMOTE_MOVE;
		}
		if (key == "down")
		{
			return EmoteConstants.ID_EMOTE_DOWN;
		}
		if (key == "come")
		{
			return EmoteConstants.ID_EMOTE_COME;
		}
		if (key == "tauntthink")
		{
			return EmoteConstants.ID_EMOTE_TAUNTTHINK;
		}
		return -1;
	}

	bool ValidTestCase(string tc)
	{
		return tc == "normal" || tc == "require_combat" || tc == "cancel_before_start" || tc == "cancel_after_start" || tc == "post_stop_watch" || tc == "interrupt_between_samples" || tc == "never_starts" || tc == "stale_callback_isolation";
	}

	DSBX_QA_EmoReq FindReqByActor(PlayerBase player)
	{
		int i = m_Reqs.Count() - 1;
		while (i >= 0)
		{
			DSBX_QA_EmoReq req = m_Reqs.Get(i);
			if (req && req.m_Actor == player && req.m_Phase != "done")
			{
				return req;
			}
			i = i - 1;
		}
		return null;
	}

	DSBX_QA_EmoReq FindReqByActorId(string actorId)
	{
		int i = m_Reqs.Count() - 1;
		while (i >= 0)
		{
			DSBX_QA_EmoReq req = m_Reqs.Get(i);
			if (req && req.m_ActorId == actorId && req.m_Phase != "done")
			{
				return req;
			}
			i = i - 1;
		}
		return null;
	}

	DSBX_QA_EmoReq FindReqByJob(string jobId)
	{
		int i = 0;
		while (i < m_Reqs.Count())
		{
			DSBX_QA_EmoReq req = m_Reqs.Get(i);
			if (req && req.m_JobId == jobId)
			{
				return req;
			}
			i = i + 1;
		}
		return null;
	}

	void RetireActorReqs(string actorId)
	{
		int i = 0;
		while (i < m_Reqs.Count())
		{
			DSBX_QA_EmoReq req = m_Reqs.Get(i);
			if (req && req.m_ActorId == actorId && req.m_Phase != "done")
			{
				if (req.m_Holding)
				{
					DropHeavy(req);
				}
				req.m_Phase = "done";
			}
			i = i + 1;
		}
	}

	void DropHeavy(DSBX_QA_EmoReq req)
	{
		if (req.m_Heavy && req.m_Actor)
		{
			// LocalDestroyEntity maneja la ubicación de manos y vacía las manos al momento.
			if (!req.m_Actor.GetHumanInventory().LocalDestroyEntity(req.m_Heavy))
			{
				g_Game.ObjectDelete(req.m_Heavy);
			}
		}
		req.m_Heavy = null;
		req.m_Holding = false;
	}

	void DoEmoteRun(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string actorId;
		string key;
		string testCase;
		if (!GetStr(args, "actor_id", actorId) || !GetStr(args, "emote_key", key) || !GetStr(args, "test_case", testCase))
		{
			Reject(res, "bad_args");
			return;
		}
		if (actorId == "" || key == "" || !ValidTestCase(testCase))
		{
			Reject(res, "bad_args");
			return;
		}
		float startTimeoutF = 5000.0;
		float finishTimeoutF = 15000.0;
		float stepF = 250.0;
		float postWatchF = -1.0;
		float combatWaitF = 5000.0;
		GetNum(args, "start_timeout_ms", startTimeoutF);
		GetNum(args, "finish_timeout_ms", finishTimeoutF);
		GetNum(args, "sample_step_ms", stepF);
		GetNum(args, "post_watch_ms", postWatchF);
		GetNum(args, "combat_wait_ms", combatWaitF);
		if (!m_Probe.IsFiniteF(startTimeoutF) || !m_Probe.IsFiniteF(finishTimeoutF) || !m_Probe.IsFiniteF(stepF) || !m_Probe.IsFiniteF(postWatchF) || !m_Probe.IsFiniteF(combatWaitF))
		{
			Reject(res, "bad_args");
			return;
		}
		if (startTimeoutF <= 0.0 || finishTimeoutF <= 0.0 || stepF <= 0.0 || combatWaitF <= 0.0)
		{
			Reject(res, "bad_args");
			return;
		}
		int emoteId = EmoteIdByKey(key);
		if (emoteId < 0)
		{
			Reject(res, "unknown_emote");
			return;
		}
		DSBX_QA_ActorRec rec = FindActor(actorId);
		if (!rec)
		{
			Reject(res, "unknown_actor");
			return;
		}
		if (!DSBX_QA_ActorRegistry.IsAvailable())
		{
			Reject(res, "expansion_unavailable");
			return;
		}
		if (testCase == "post_stop_watch")
		{
			StartPostStopWatch(op, rec, stepF, postWatchF, res);
			return;
		}
		// Efecto operativo (gesto, objeto en manos): guarda de lease antes de emitir (E1).
		if (!m_Probe.LeaseOk())
		{
			Fail(res, "lease_expired");
			return;
		}
		PlayerBase ent = rec.m_Ent;
		EmoteManager em = ent.GetEmoteManager();
		if (!em)
		{
			Fail(res, "no_emote_manager");
			return;
		}
		string err = m_Jobs.StartJob(this, op.op_id, "actor:" + actorId, m_EmoNcol, m_EmoScol, 4, 4096, startTimeoutF + finishTimeoutF + combatWaitF + 60000.0, "stop");
		if (err != "")
		{
			Reject(res, err);
			return;
		}
		RetireActorReqs(actorId);
		DSBX_QA_EmoReq req = new DSBX_QA_EmoReq();
		m_ReqCounter = m_ReqCounter + 1;
		req.m_ReqSeq = m_ReqCounter;
		req.m_JobId = op.op_id;
		req.m_ActorId = actorId;
		req.m_Actor = ent;
		req.m_Rec = rec;
		req.m_EmoteKey = key;
		req.m_TestCase = testCase;
		req.m_Fault = m_Probe.GetOpFault();
		req.m_ExpEmoteId = emoteId;
		req.m_PlayEmoteId = emoteId;
		if (req.m_Fault == "wrong_emote_played")
		{
			// Mutante: el actor ejecuta el gesto de al lado; lo esperado sigue siendo el pedido.
			req.m_PlayEmoteId = emoteId + 1;
		}
		req.m_StartTimeoutMs = startTimeoutF;
		req.m_FinishTimeoutMs = finishTimeoutF;
		req.m_StepMs = stepF;
		req.m_CombatWaitMs = combatWaitF;
		req.m_PostWatchMs = postWatchF;
		if (postWatchF < 0.0)
		{
			req.m_PostWatchMs = 0.0;
			if (testCase != "normal" && testCase != "require_combat")
			{
				req.m_PostWatchMs = 3000.0;
			}
		}
		req.m_ExpCmdId = ExpectedCmd(em, emoteId);
		req.m_NextSampleMs = stepF;
		float now = NowMs();
		req.m_WaitStartTick = now;
		m_Reqs.Insert(req);
		bool hold = testCase == "cancel_before_start" || testCase == "never_starts" || testCase == "interrupt_between_samples";
		if (hold)
		{
			EntityAI heavy = ent.GetHumanInventory().CreateInHands(DSBX_QA_ACT_HEAVY_CLASS);
			NoteEffect();
			if (!heavy)
			{
				req.m_Phase = "done";
				m_Jobs.EndJob(op.op_id, "failed", "hold_failed");
				Fail(res, "spawn_failed");
				return;
			}
			req.m_Heavy = heavy;
			req.m_Holding = true;
		}
		if (testCase == "stale_callback_isolation")
		{
			// Un callback previo (anterior a la petición) que termina durante ella: no se le atribuye nada.
			em.PlayEmote(EmoteConstants.ID_EMOTE_GREETING);
		}
		req.m_MaxCbAtReq = EmoteCB.DsbxCbCounter();
		if (testCase == "require_combat")
		{
			req.m_Phase = "wait_combat";
		}
		else
		{
			IssueRequest(req, now, testCase != "stale_callback_isolation");
		}
		m_Jobs.FillStartRead(res.read, op.op_id, "actor:" + actorId);
	}

	// cmd esperado: lo que EmoteManager decide para ese gesto con la postura actual (no se copia de la fixture).
	int ExpectedCmd(EmoteManager em, int emoteId)
	{
		EmoteBase emote;
		if (!em.GetNameEmoteMap().Find(emoteId, emote) || !emote)
		{
			return 0;
		}
		int cmd = 0;
		int stanceMask = 0;
		bool fullBody = false;
		if (!em.DetermineEmoteData(emote, cmd, stanceMask, fullBody))
		{
			return 0;
		}
		return cmd;
	}

	// Registra la petición (req_tick_ms) y la manda al actor. Antes de pedir, deja una fila «pedido».
	void IssueRequest(DSBX_QA_EmoReq req, float now, bool sendToActor)
	{
		req.m_ReqTick = now;
		req.m_Phase = "active";
		req.m_State = "pedido";
		EmitEmoRow(req, "event", now);
		if (sendToActor)
		{
			DSBX_QA_ActorRegistry.Get().SetEmote(req.m_Actor, req.m_PlayEmoteId);
			NoteEffect();
		}
	}

	void StartPostStopWatch(DSBX_QA_Op op, DSBX_QA_ActorRec rec, float stepF, float postWatchF, DSBX_QA_Result res)
	{
		DSBX_QA_EmoReq req = FindReqByActorId(rec.m_Id);
		if (!req || req.m_CancelRequested == 0 || req.m_JobId != "")
		{
			Reject(res, "bad_args");
			return;
		}
		string err = m_Jobs.StartJob(this, op.op_id, "actor:" + rec.m_Id, m_EmoNcol, m_EmoScol, 4, 4096, 120000.0, "stop");
		if (err != "")
		{
			Reject(res, err);
			return;
		}
		req.m_JobId = op.op_id;
		req.m_StepMs = stepF;
		string postFault = m_Probe.GetOpFault();
		if (postFault != "")
		{
			req.m_Fault = postFault;
		}
		if (postWatchF >= 0.0)
		{
			req.m_PostWatchMs = postWatchF;
		}
		else
		{
			req.m_PostWatchMs = 3000.0;
		}
		req.m_NextSampleMs = req.m_DtsumMs + stepF;
		// Vuelca las filas retenidas desde el stop, con su req_seq_n, y sigue muestreando.
		int i = 0;
		while (i < req.m_Retained.Count())
		{
			DSBX_QA_EmoRow row = req.m_Retained.Get(i);
			m_Jobs.AppendRow(op.op_id, row.m_N, row.m_S);
			i = i + 1;
		}
		req.m_Retained.Clear();
		m_Jobs.FillStartRead(res.read, op.op_id, "actor:" + rec.m_Id);
	}

	// ---------------------------------------------------------------- observador de gestos (eventos de EmoteCB)

	void EmoOnBound(PlayerBase player, int cbInstId, int gestureId, int cmdId)
	{
		if (!player)
		{
			return;
		}
		DSBX_QA_EmoReq req = FindReqByActor(player);
		if (!req)
		{
			return;
		}
		if (req.m_ReqTick <= 0.0)
		{
			// Aún no hay petición emitida (esperando combate): ningún callback es suyo.
			return;
		}
		if (cbInstId > req.m_MaxCbAtReq && req.m_CbInst == 0 && req.m_CancelRequested == 0)
		{
			req.m_CbInst = cbInstId;
			req.m_ObsEmoteId = gestureId;
			req.m_AnimCmd = cmdId;
			return;
		}
		req.m_Foreign = req.m_Foreign + 1;
		if (cbInstId > req.m_MaxCbAtReq && req.m_CancelRequested == 1)
		{
			req.m_PostCleanupCb = req.m_PostCleanupCb + 1;
		}
	}

	void EmoOnState(PlayerBase player, int cbInstId, int oldState, int newState)
	{
		if (!player)
		{
			return;
		}
		DSBX_QA_EmoReq req = FindReqByActor(player);
		if (!req || req.m_CbInst == 0 || cbInstId != req.m_CbInst)
		{
			return;
		}
		if (oldState == 0 && newState != 0 && req.m_StartTick <= 0.0)
		{
			req.m_AnimState = newState;
			req.m_StartTick = NowMs();
			if (req.m_State == "pedido")
			{
				req.m_State = "en_curso";
			}
			req.m_EvStart = true;
		}
	}

	void EmoOnFinish(PlayerBase player, int cbInstId, bool canceled)
	{
		if (!player)
		{
			return;
		}
		DSBX_QA_EmoReq req = FindReqByActor(player);
		if (!req)
		{
			return;
		}
		if (req.m_CbInst != 0 && cbInstId == req.m_CbInst)
		{
			FinishBound(req, canceled);
			return;
		}
		if (req.m_ReqTick <= 0.0)
		{
			return;
		}
		// Callback ajeno o previo a la petición.
		if (req.m_Fault == "accept_stale_cb" && req.m_CbInst == 0 && req.m_CancelRequested == 0 && cbInstId <= req.m_MaxCbAtReq)
		{
			// Mutante: omite el filtro de instancia y atribuye el OnFinish del callback anterior a la petición nueva.
			req.m_CbInst = cbInstId;
			FinishBound(req, canceled);
			return;
		}
		req.m_Foreign = req.m_Foreign + 1;
	}

	void FinishBound(DSBX_QA_EmoReq req, bool canceled)
	{
		req.m_OnFinish = 1;
		req.m_EndTick = NowMs();
		if (canceled)
		{
			req.m_RawCanceled = 1;
			req.m_EndCause = "cb_canceled";
			req.m_State = "cancelado";
		}
		else
		{
			req.m_RawCanceled = 0;
			req.m_EndCause = "cb_normal";
			req.m_State = "terminado";
			if (req.m_CancelRequested == 0)
			{
				// Al terminar normal se retira también la petición interna de Expansion.
				DSBX_QA_ActorRegistry.Get().SetEmote(req.m_Actor, 0);
			}
		}
		req.m_EvFinish = true;
	}

	// ---------------------------------------------------------------- act_emote_run: bucle por tick

	// Una fila del trabajo de gesto: 35 numéricas y 6 de texto en el orden del brief §3, lecturas vivas del motor.
	void BuildEmoRow(DSBX_QA_EmoReq req, string kind, float now, array<float> n, array<string> s)
	{
		PlayerBase a = req.m_Actor;
		DSBX_QA_ActorRec rec = req.m_Rec;
		DSBX_QA_ActorBackend backend = DSBX_QA_ActorRegistry.Get();
		float stance = -1.0;
		float hands = 0.0;
		float canPlay = 0.0;
		float playing = 0.0;
		float cbPresent = 0.0;
		float pending = 0.0;
		float fighting = 0.0;
		float raised = 0.0;
		float health = 0.0;
		string faction = "";
		if (a)
		{
			HumanMovementState ms = new HumanMovementState();
			a.GetMovementState(ms);
			stance = ms.m_iStanceIdx;
			hands = BoolF(a.GetItemInHands() == null);
			EmoteManager em = a.GetEmoteManager();
			if (em)
			{
				canPlay = BoolF(em.CanPlayEmote(req.m_ExpEmoteId));
				playing = BoolF(em.m_bEmoteIsPlaying);
				cbPresent = BoolF(em.m_Callback != null);
			}
			pending = backend.PendingEmote(a);
			fighting = BoolF(a.IsFighting());
			raised = BoolF(a.IsRaised());
			health = a.GetHealth("", "");
			faction = backend.FactionClass(a);
		}
		int rawOut = req.m_RawCanceled;
		string causeOut = req.m_EndCause;
		string stateOut = req.m_State;
		if (req.m_Fault == "canceled_as_done" && req.m_RawCanceled == 1)
		{
			// Mutante: tras Cancel() falsea la causa del fin y da el gesto por terminado.
			rawOut = 0;
			causeOut = "cb_normal";
			stateOut = "terminado";
		}
		float pseq = -1.0;
		if (kind == "periodic")
		{
			pseq = req.m_PeriodicSeq;
		}
		n.Insert(req.m_RowSeq);
		n.Insert(pseq);
		n.Insert(m_Probe.m_Frame);
		n.Insert(now);
		n.Insert(req.m_DtsumMs);
		n.Insert(req.m_ReqSeq);
		n.Insert(req.m_CbInst);
		n.Insert(req.m_MaxCbAtReq);
		n.Insert(req.m_ExpEmoteId);
		n.Insert(req.m_ObsEmoteId);
		n.Insert(req.m_ExpCmdId);
		n.Insert(req.m_AnimCmd);
		n.Insert(req.m_AnimState);
		n.Insert(req.m_OnFinish);
		n.Insert(rawOut);
		n.Insert(req.m_CancelRequested);
		n.Insert(stance);
		n.Insert(hands);
		n.Insert(canPlay);
		n.Insert(playing);
		n.Insert(cbPresent);
		n.Insert(pending);
		n.Insert(req.m_PostCleanupCb);
		n.Insert(req.m_Foreign);
		n.Insert(req.m_ReqTick);
		n.Insert(req.m_StartTick);
		n.Insert(req.m_CancelReqTick);
		n.Insert(req.m_EndTick);
		n.Insert(req.m_CleanupTick);
		n.Insert(fighting);
		n.Insert(raised);
		n.Insert(health);
		n.Insert(InfHealth(rec));
		n.Insert(InfDisp(rec));
		n.Insert(now);
		s.Insert(req.m_EmoteKey);
		s.Insert(kind);
		s.Insert(stateOut);
		s.Insert(causeOut);
		s.Insert(rec.m_InfId);
		s.Insert(faction);
	}

	void EmitEmoRow(DSBX_QA_EmoReq req, string kind, float now)
	{
		DSBX_QA_EmoRow row = new DSBX_QA_EmoRow();
		BuildEmoRow(req, kind, now, row.m_N, row.m_S);
		req.m_RowSeq = req.m_RowSeq + 1;
		if (kind == "periodic")
		{
			req.m_PeriodicSeq = req.m_PeriodicSeq + 1;
		}
		// Historial de observaciones de combate (mismas filas que verá el evaluador), máx. 8.
		req.m_HistTick.Insert(now);
		req.m_HistAh.Insert(row.m_N.Get(31));
		req.m_HistIh.Insert(row.m_N.Get(32));
		req.m_HistDisp.Insert(row.m_N.Get(33));
		while (req.m_HistTick.Count() > 8)
		{
			req.m_HistTick.RemoveOrdered(0);
			req.m_HistAh.RemoveOrdered(0);
			req.m_HistIh.RemoveOrdered(0);
			req.m_HistDisp.RemoveOrdered(0);
		}
		if (req.m_JobId != "" && m_Jobs.GetState(req.m_JobId) == "running")
		{
			m_Jobs.AppendRow(req.m_JobId, row.m_N, row.m_S);
		}
		else
		{
			req.m_Retained.Insert(row);
			while (req.m_Retained.Count() > 256)
			{
				req.m_Retained.RemoveOrdered(0);
			}
		}
	}

	// Combate vigente (brief §2.3, N27): objetivo vivo, actor vivo, facción hostil y actividad de combate actual.
	bool ActiveCombatNow(DSBX_QA_EmoReq req, float now)
	{
		DSBX_QA_ActorRec rec = req.m_Rec;
		PlayerBase a = req.m_Actor;
		if (!a || rec.m_InfId == "")
		{
			return false;
		}
		float ih = InfHealth(rec);
		float ah = ActorHealth(rec);
		if (ih <= 0.0 || ah <= 0.0)
		{
			return false;
		}
		string faction = DSBX_QA_ActorRegistry.Get().FactionClass(a);
		if (faction == "" || faction == "eAIFactionPassive" || faction == "eAIFactionCivilian")
		{
			return false;
		}
		if (a.IsFighting())
		{
			return true;
		}
		if (!a.IsRaised())
		{
			return false;
		}
		float disp = InfDisp(rec);
		int j = req.m_HistTick.Count() - 1;
		while (j >= 0)
		{
			float dt = now - req.m_HistTick.Get(j);
			if (dt > 0.0)
			{
				if (dt > 1000.0)
				{
					return false;
				}
				if (req.m_HistAh.Get(j) - ah > 0.0 || req.m_HistIh.Get(j) - ih > 0.0 || disp - req.m_HistDisp.Get(j) >= 0.25)
				{
					return true;
				}
			}
			j = j - 1;
		}
		return false;
	}

	// Solicitud de cancelación: SetEmote(0), suelta el objeto pesado y pide Cancel() del callback vivo.
	// La fila de solicitud y la de limpieza completada se emiten desde TickEmote.
	void BeginCancel(DSBX_QA_EmoReq req, float now, string newState, string stopKind)
	{
		if (req.m_CancelRequested == 1)
		{
			return;
		}
		req.m_CancelRequested = 1;
		req.m_CancelReqTick = now;
		req.m_StopKind = stopKind;
		if (req.m_State == "pedido" || req.m_State == "en_curso")
		{
			req.m_State = newState;
		}
		bool skipClear = false;
		if (req.m_Fault == "no_clear_on_timeout" && stopKind == "timeout")
		{
			skipClear = true;
		}
		if (req.m_Fault == "no_clear_after_start" && stopKind == "stop" && req.m_StartTick > 0.0)
		{
			skipClear = true;
		}
		if (!skipClear)
		{
			DSBX_QA_ActorRegistry.Get().SetEmote(req.m_Actor, 0);
		}
		if (req.m_Holding)
		{
			DropHeavy(req);
		}
		if (req.m_Actor)
		{
			EmoteManager em = req.m_Actor.GetEmoteManager();
			if (em && em.m_Callback)
			{
				em.m_Callback.Cancel();
			}
		}
		req.m_Phase = "cancelling";
		req.m_CancelTimerMs = now;
		req.m_CancelRowDone = false;
		req.m_CleanupRowDone = false;
	}

	bool CleanupConditions(DSBX_QA_EmoReq req)
	{
		PlayerBase a = req.m_Actor;
		if (!a)
		{
			return false;
		}
		EmoteManager em = a.GetEmoteManager();
		if (!em)
		{
			return false;
		}
		if (em.m_Callback || em.m_bEmoteIsPlaying)
		{
			return false;
		}
		if (req.m_CbInst != 0 && req.m_OnFinish == 0)
		{
			return false;
		}
		return em.CanPlayEmote(req.m_ExpEmoteId);
	}

	void TickEmote(DSBX_QA_EmoReq req, float timeslice)
	{
		float now = NowMs();
		req.m_DtsumMs = req.m_DtsumMs + timeslice * 1000.0;
		// El trabajo ligado murió por su cuenta (stop, expiración, lease): las filas pasan a la reserva.
		if (req.m_JobId != "")
		{
			string st = m_Jobs.GetState(req.m_JobId);
			if (st != "running")
			{
				req.m_JobId = "";
			}
			else
			{
				if (m_Jobs.IsDeadmanTripped(req.m_JobId))
				{
					m_Jobs.EndJob(req.m_JobId, "failed", "lease_expired");
					return;
				}
			}
		}
		if (!req.m_Actor || !req.m_Rec)
		{
			req.m_Phase = "done";
			if (req.m_JobId != "")
			{
				m_Jobs.EndJob(req.m_JobId, "failed", "actor_lost");
			}
			return;
		}
		if (req.m_Phase == "done")
		{
			return;
		}
		if (req.m_Phase == "wait_combat")
		{
			TickWaitCombat(req, now);
		}
		else
		{
			TickRequest(req, now);
		}
		// Muestras periódicas (por Σtimeslice del gesto).
		if (req.m_Phase != "done" && req.m_DtsumMs >= req.m_NextSampleMs)
		{
			req.m_NextSampleMs = req.m_NextSampleMs + req.m_StepMs;
			if (req.m_NextSampleMs <= req.m_DtsumMs)
			{
				req.m_NextSampleMs = req.m_DtsumMs + req.m_StepMs;
			}
			EmitEmoRow(req, "periodic", now);
			req.m_FirstPeriodicDone = true;
		}
		// Fin del trabajo: asentado y vigilada la ventana de quietud.
		if (req.m_Phase == "settled")
		{
			if (now - req.m_SettleTick >= req.m_PostWatchMs && req.m_JobId != "")
			{
				string jobToEnd = req.m_JobId;
				req.m_JobId = "";
				req.m_Phase = "done";
				// Limpieza de seguridad tras la última fila: no deja peticiones pendientes en el actor.
				DSBX_QA_ActorRegistry.Get().SetEmote(req.m_Actor, 0);
				m_Jobs.EndJob(jobToEnd, "done", "");
			}
			else
			{
				if (req.m_JobId == "")
				{
					if (req.m_RetireTick <= 0.0)
					{
						req.m_RetireTick = now + 20000.0;
					}
					if (now >= req.m_RetireTick)
					{
						req.m_Phase = "done";
						DSBX_QA_ActorRegistry.Get().SetEmote(req.m_Actor, 0);
					}
				}
			}
		}
	}

	void TickWaitCombat(DSBX_QA_EmoReq req, float now)
	{
		if (m_Jobs.IsDeadmanTripped(req.m_JobId))
		{
			return;
		}
		if (ActiveCombatNow(req, now))
		{
			// Combate vigente acreditado en esta observación: la petición sale en el mismo tick.
			req.m_CombatObsTick = now;
			if (!m_Probe.LeaseOk())
			{
				return;
			}
			IssueRequest(req, now, req.m_Fault != "combat_emote_as_done");
			if (req.m_Fault == "combat_emote_as_done")
			{
				// Mutante: ignora el combate y da el gesto por terminado.
				req.m_OnFinish = 1;
				req.m_RawCanceled = 0;
				req.m_EndCause = "cb_normal";
				req.m_State = "terminado";
				req.m_EndTick = now;
				req.m_EvFinish = true;
				return;
			}
			EmoteManager em = req.m_Actor.GetEmoteManager();
			if (em && !em.CanPlayEmote(req.m_ExpEmoteId))
			{
				// El gestor de gestos rechaza con el actor en combate.
				BeginCancel(req, now, "rechazado", "reject");
			}
			return;
		}
		if (now - req.m_WaitStartTick >= req.m_CombatWaitMs)
		{
			// Sin combate vigente acreditado: sin petición (el evaluador da INCONCLUSO).
			req.m_State = "agotado";
			req.m_Phase = "settled";
			req.m_SettleTick = now;
		}
	}

	void TickRequest(DSBX_QA_EmoReq req, float now)
	{
		if (req.m_EvStart)
		{
			req.m_EvStart = false;
			EmitEmoRow(req, "event", now);
		}
		if (req.m_EvFinish)
		{
			req.m_EvFinish = false;
			EmitEmoRow(req, "event", now);
			if (req.m_Phase == "active")
			{
				req.m_Phase = "settled";
				req.m_SettleTick = req.m_EndTick;
			}
		}
		if (req.m_Phase == "active")
		{
			TickActive(req, now);
		}
		if (req.m_Phase == "cancelling")
		{
			TickCancelling(req, now);
		}
	}

	void TickActive(DSBX_QA_EmoReq req, float now)
	{
		if (req.m_TestCase == "stale_callback_isolation")
		{
			if (req.m_Foreign >= 1)
			{
				req.m_State = "agotado";
				BeginCancel(req, now, "agotado", "timeout");
				return;
			}
		}
		if (req.m_TestCase == "interrupt_between_samples")
		{
			// Retiene el inicio hasta justo después de la muestra periódica P_k y corta a 80 ms de P_{k+1}.
			if (req.m_Holding && req.m_FirstPeriodicDone)
			{
				DropHeavy(req);
				NoteEffect();
			}
			if (!req.m_Holding && req.m_FirstPeriodicDone && req.m_CancelRequested == 0)
			{
				float untilNext = req.m_NextSampleMs - req.m_DtsumMs;
				if (untilNext <= 80.0)
				{
					BeginCancel(req, now, "cancelado", "interrupt");
					return;
				}
			}
		}
		if (req.m_StartTick <= 0.0)
		{
			if (now - req.m_ReqTick >= req.m_StartTimeoutMs)
			{
				BeginCancel(req, now, "agotado", "timeout");
			}
			return;
		}
		if (req.m_OnFinish == 0 && now - req.m_StartTick >= req.m_FinishTimeoutMs)
		{
			BeginCancel(req, now, "agotado", "timeout");
		}
	}

	void TickCancelling(DSBX_QA_EmoReq req, float now)
	{
		bool ready = CleanupConditions(req);
		if (!req.m_CancelRowDone)
		{
			if (req.m_CbInst == 0 && ready)
			{
				// Ningún callback había empezado: la solicitud y la limpieza completada coinciden (misma fila).
				req.m_CleanupTick = req.m_CancelReqTick;
				req.m_CancelRowDone = true;
				req.m_CleanupRowDone = true;
				EmitEmoRow(req, "event", now);
				SettleAfterCleanup(req, now);
				return;
			}
			if (req.m_CbInst != 0 || now - req.m_CancelReqTick >= 1000.0)
			{
				req.m_CancelRowDone = true;
				EmitEmoRow(req, "event", now);
			}
		}
		if (req.m_CancelRowDone && !req.m_CleanupRowDone)
		{
			if (ready)
			{
				req.m_CleanupTick = now;
				req.m_CleanupRowDone = true;
				EmitEmoRow(req, "event", now);
				SettleAfterCleanup(req, now);
			}
			else
			{
				if (now - req.m_CancelReqTick >= 1000.0 + req.m_PostWatchMs)
				{
					// La limpieza no llegó a completarse: se aborta la vigilancia (el evaluador lo verá).
					req.m_Phase = "settled";
					req.m_SettleTick = now - req.m_PostWatchMs;
				}
			}
		}
	}

	void SettleAfterCleanup(DSBX_QA_EmoReq req, float now)
	{
		req.m_Phase = "settled";
		req.m_SettleTick = req.m_CleanupTick;
		if (req.m_SettleTick < req.m_CancelReqTick)
		{
			req.m_SettleTick = now;
		}
	}

	// ---------------------------------------------------------------- tick y fin de trabajos

	override void OnTick(float timeslice)
	{
		int b = 0;
		while (b < m_BehRuns.Count())
		{
			DSBX_QA_BehRun run = m_BehRuns.Get(b);
			int before = m_BehRuns.Count();
			if (run)
			{
				TickBehaviour(run, timeslice);
			}
			// OnJobEnd quita la ejecución de la lista: no se salta la siguiente.
			if (m_BehRuns.Count() == before)
			{
				b = b + 1;
			}
		}
		int r = 0;
		while (r < m_Reqs.Count())
		{
			DSBX_QA_EmoReq req = m_Reqs.Get(r);
			if (req && req.m_Phase != "done")
			{
				TickEmote(req, timeslice);
			}
			r = r + 1;
		}
		// Compacta las peticiones terminadas.
		int c = m_Reqs.Count() - 1;
		while (c >= 0)
		{
			DSBX_QA_EmoReq dead = m_Reqs.Get(c);
			if (!dead || (dead.m_Phase == "done" && dead.m_JobId == ""))
			{
				m_Reqs.RemoveOrdered(c);
			}
			c = c - 1;
		}
	}

	void SafetyCleanup(DSBX_QA_EmoReq req)
	{
		// Limpieza de seguridad: corre siempre, también con el lease caducado.
		if (req.m_Actor)
		{
			DSBX_QA_ActorRegistry.Get().SetEmote(req.m_Actor, 0);
			if (req.m_Holding)
			{
				DropHeavy(req);
			}
			EmoteManager em = req.m_Actor.GetEmoteManager();
			if (em && em.m_Callback)
			{
				em.m_Callback.Cancel();
			}
		}
		req.m_Phase = "done";
	}

	override void OnJobEnd(string job_id, string state, string reason)
	{
		int b = 0;
		while (b < m_BehRuns.Count())
		{
			DSBX_QA_BehRun run = m_BehRuns.Get(b);
			if (run && run.m_JobId == job_id)
			{
				StopActorMotion(run.m_Rec.m_Ent);
				m_BehRuns.RemoveOrdered(b);
				return;
			}
			b = b + 1;
		}
		DSBX_QA_EmoReq req = FindReqByJob(job_id);
		if (!req)
		{
			return;
		}
		req.m_JobId = "";
		if (state == "done")
		{
			return;
		}
		if (state == "stopped" && reason != "shutdown")
		{
			// job_stop: el gesto pendiente o en curso se cancela; las filas siguientes quedan retenidas en el actor
			// (nunca se escribe en el trabajo detenido) para el trabajo post_stop_watch.
			if (req.m_Phase == "active" || req.m_Phase == "wait_combat")
			{
				if (req.m_ReqTick > 0.0)
				{
					BeginCancel(req, NowMs(), "cancelado", "stop");
				}
				else
				{
					SafetyCleanup(req);
				}
			}
			return;
		}
		SafetyCleanup(req);
	}

	override void OnShutdown()
	{
		int r = 0;
		while (r < m_Reqs.Count())
		{
			DSBX_QA_EmoReq req = m_Reqs.Get(r);
			if (req)
			{
				SafetyCleanup(req);
			}
			r = r + 1;
		}
		m_Reqs.Clear();
		int b = 0;
		while (b < m_BehRuns.Count())
		{
			DSBX_QA_BehRun run = m_BehRuns.Get(b);
			if (run)
			{
				StopActorMotion(run.m_Rec.m_Ent);
			}
			b = b + 1;
		}
		m_BehRuns.Clear();
		DSBX_QA_EmoteHub.SetSink(null);
		// Borra solo lo propio (registrado en memoria).
		DSBX_QA_ActorBackend backend = DSBX_QA_ActorRegistry.Get();
		int i = 0;
		while (i < m_Actors.Count())
		{
			DSBX_QA_ActorRec rec = m_Actors.Get(i);
			if (rec && rec.m_Ent)
			{
				backend.ReleaseActor(rec.m_Ent);
				g_Game.ObjectDelete(rec.m_Ent);
			}
			i = i + 1;
		}
		m_Actors.Clear();
		int p = 0;
		while (p < m_Props.Count())
		{
			if (m_Props.Get(p))
			{
				g_Game.ObjectDelete(m_Props.Get(p));
			}
			p = p + 1;
		}
		m_Props.Clear();
		int q = 0;
		while (q < m_Infected.Count())
		{
			if (m_Infected.Get(q))
			{
				g_Game.ObjectDelete(m_Infected.Get(q));
			}
			q = q + 1;
		}
		m_Infected.Clear();
	}
}
