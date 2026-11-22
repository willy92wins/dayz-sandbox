// DSBX_QA_X_Persist.c — S-persist server-only extension (F0.3b).
// Handles verbs with prefix "per_" on role == "server".
// Ordered arrays (m_Records, m_SceneIds, m_SceneGen, m_SceneLastOp, m_SceneLastRetainedSkipped, m_RawRecords)
// use RemoveOrdered exclusively (rule E3).

class DSBX_QA_PersistRecord : Managed
{
	string m_ServerEpoch;
	string m_SceneId;
	int m_GenN;
	string m_LogicalId;
	string m_ParentId;
	string m_Cat;
	string m_ClassName;
	string m_SlotName;
	string m_NetId;
	string m_PersId;
	float m_ReqXM;
	float m_ReqYM;
	float m_ReqZM;
	float m_ReqYawDeg;
	float m_HealthMarkRatio;
	int m_MustVanishB;
	float m_SpawnTickMs;
	float m_MaxHp;
	float m_HealthHp;
	int m_HealthMarkB;
	int m_OkB;
	int m_AliveB;
	int m_AiAgentB;
	float m_Q9XM;
	float m_Q9YM;
	float m_Q9ZM;
	float m_Q9DxM;
	float m_Q9DyM;
	float m_Q9DzM;
	float m_Q9Err3dM;
	float m_Q9YawDeg;
	float m_Q9PitchDeg;
	float m_Q9RollDeg;
	string m_ObsLocKind;
	string m_ObsParentNetId;
	string m_ObsSlotName;
	bool m_RetainOnReset;
	int m_ForeignDescendantsN;
	int m_BornInInventory;
	Object m_RefEnt;

	void DSBX_QA_PersistRecord()
	{
		m_ServerEpoch = "";
		m_SceneId = "";
		m_GenN = 1;
		m_LogicalId = "";
		m_ParentId = "";
		m_Cat = "prop";
		m_ClassName = "";
		m_SlotName = "";
		m_NetId = "0:0";
		m_PersId = "0:0:0:0";
		m_ReqXM = 0.0;
		m_ReqYM = 0.0;
		m_ReqZM = 0.0;
		m_ReqYawDeg = 0.0;
		m_HealthMarkRatio = 1.0;
		m_MustVanishB = 1;
		m_SpawnTickMs = 0.0;
		m_MaxHp = 100.0;
		m_HealthHp = 100.0;
		m_HealthMarkB = 1;
		m_OkB = 0;
		m_AliveB = 0;
		m_AiAgentB = 0;
		m_Q9XM = 0.0;
		m_Q9YM = 0.0;
		m_Q9ZM = 0.0;
		m_Q9DxM = 0.0;
		m_Q9DyM = 0.0;
		m_Q9DzM = 0.0;
		m_Q9Err3dM = 0.0;
		m_Q9YawDeg = 0.0;
		m_Q9PitchDeg = 0.0;
		m_Q9RollDeg = 0.0;
		m_ObsLocKind = "ground";
		m_ObsParentNetId = "";
		m_ObsSlotName = "";
		m_RetainOnReset = false;
		m_ForeignDescendantsN = 0;
		m_BornInInventory = 0;
		m_RefEnt = null;
	}
}

class DSBX_QA_PersistRawRecord : Managed
{
	string m_Tag;
	string m_Mode;
	string m_ClassName;
	string m_NetId;
	string m_PersId;
	float m_SpawnTickMs;
	float m_MaxHp;
	float m_HealthHp;
	int m_HealthMarkB;
	Object m_RefEnt;
	Object m_ChildEnt;

	void DSBX_QA_PersistRawRecord()
	{
		m_Tag = "";
		m_Mode = "";
		m_ClassName = "";
		m_NetId = "0:0";
		m_PersId = "0:0:0:0";
		m_SpawnTickMs = 0.0;
		m_MaxHp = 100.0;
		m_HealthHp = 100.0;
		m_HealthMarkB = 1;
		m_RefEnt = null;
		m_ChildEnt = null;
	}
}

class DSBX_QA_PersistWitnessFollow : Managed
{
	Object m_Ent;
	string m_ClassName;
	string m_NetId;
	string m_ParentNetId;
	float m_LastX;
	float m_LastY;
	float m_LastZ;
	float m_LastYawDeg;
	float m_EEInitTickMs;
	int m_EEInitFrame;
	int m_AiAgentB;
	bool m_PendingSample0;
	int m_NextSample;

	void DSBX_QA_PersistWitnessFollow()
	{
		m_Ent = null;
		m_ClassName = "";
		m_NetId = "0:0";
		m_ParentNetId = "";
		m_LastX = 0.0;
		m_LastY = 0.0;
		m_LastZ = 0.0;
		m_LastYawDeg = 0.0;
		m_EEInitTickMs = 0.0;
		m_EEInitFrame = 0;
		m_AiAgentB = 0;
		m_PendingSample0 = false;
		m_NextSample = 1;
	}
}

class DSBX_QA_X_Persist : DSBX_QA_Ext
{
	static const int FLAG_ECE_CREATEPHYSICS = 1024;
	static const int FLAG_ECE_INITAI = 2048;
	static const int FLAG_ECE_NOLIFETIME = 4194304;
	static const int FLAG_ECE_NOPERSISTENCY_WORLD = 8388608;
	static const int FLAG_ECE_NOPERSISTENCY_CHAR = 16777216;
	static const int FLAG_ECE_IN_INVENTORY = 787456;
	static const int FLAG_ECE_PLACE_ON_SURFACE = 1060;
	static const int FLAG_RF_DEFAULT = 512;

	static const float CENSUS_ALL_RADIUS_MAX = 120.0;
	static const float WITNESS_RADIUS_MAX = 120.0;
	static const float WITNESS_WINDOW_MAX_MS = 600000.0;
	static const float WITNESS_TAIL_MS = 5000.0;
	static const int WITNESS_K_DEFAULT = 3;
	static const int WITNESS_K_MAX = 5;

	static const int FLAGS_STATIC = 29361188;
	static const int FLAGS_AI_A = 29363236;
	static const int FLAGS_AI_B = 29361188;
	static const int FLAGS_INV_OWN = 30147584;

	protected ref array<ref DSBX_QA_PersistRecord> m_Records;
	protected ref array<string> m_SceneIds;
	protected ref array<int> m_SceneGen;
	protected ref array<string> m_SceneLastOp;
	protected ref array<int> m_SceneLastRetainedSkipped;
	protected ref array<ref DSBX_QA_PersistRawRecord> m_RawRecords;
	protected ref array<string> m_SentinelClasses;
	protected ref array<string> m_CensusNcol;
	protected ref array<string> m_CensusScol;
	protected ref array<string> m_CensusNcolAll;
	protected ref array<string> m_WitnessNcol;
	protected ref array<string> m_WitnessScol;
	protected ref array<ref DSBX_QA_PersistWitnessFollow> m_WitnessFollow;
	protected string m_WitnessJobId;
	protected float m_WitnessEndMs;
	protected int m_WitnessK;
	protected bool m_WitnessWindowClosed;
	protected ref array<string> m_PendingFinishIds;
	protected ref array<int> m_PendingFinishTicks;
	protected ref array<int> m_PendingFinishSeen;
	protected ref array<float> m_PendingFinishAgeMs;
	protected float m_CensusCaptureStartMs;
	protected float m_CensusLeaseAgeStartMs;
	protected bool m_CaptureFailed;
	protected string m_CaptureFailReason;
	protected string m_CaptureFailJobId;
	protected int m_LastApplyRetainedSkipped;
	protected bool m_PersistRawKitOk;
	// P2c: la purga la ordena el runner con su lista de pers_id (trabajo per_purge).
	protected ref array<string> m_PurgeAuthPersIds;
	protected ref array<string> m_PurgeAuthClasses;
	protected ref array<int> m_PurgeResolved;
	protected string m_PurgeJobId;
	protected string m_PurgeDirectorUid;
	protected string m_PurgeConfirmPersId;
	protected string m_PurgeConfirmClass;
	protected string m_PurgeConfirmNetId;
	protected string m_PurgeConfirmParentPersId;
	protected string m_PurgeConfirmParentNetId;
	protected float m_PurgeConfirmEmitTick;
	protected int m_PurgePreN;
	static const float PURGE_MAX_DURATION_MS = 600000.0;
	// Presupuesto verificable de captura del censo (MEN-14); el cupo de filas llega por StartJob.
	static const float CENSUS_CAPTURE_BUDGET_MS = 120000.0;
	// BLOQ 6: A retiene per_census hasta acreditar el intento de B; salida acotada.
	static const float CENSUS_HOLD_MAX_MS = 750.0;
	static const int CENSUS_FINISH_AFTER_ATTEMPT_TICKS = 2;

	void DSBX_QA_X_Persist()
	{
		m_Records = new array<ref DSBX_QA_PersistRecord>();
		m_SceneIds = new array<string>();
		m_SceneGen = new array<int>();
		m_SceneLastOp = new array<string>();
		m_SceneLastRetainedSkipped = new array<int>();
		m_RawRecords = new array<ref DSBX_QA_PersistRawRecord>();
		m_SentinelClasses = new array<string>();
		m_CensusNcol = new array<string>();
		m_CensusScol = new array<string>();
		m_CensusNcolAll = new array<string>();
		m_WitnessNcol = new array<string>();
		m_WitnessScol = new array<string>();
		m_WitnessFollow = new array<ref DSBX_QA_PersistWitnessFollow>();
		m_WitnessJobId = "";
		m_WitnessEndMs = 0.0;
		m_WitnessK = 0;
		m_WitnessWindowClosed = false;
		m_PendingFinishIds = new array<string>();
		m_PendingFinishTicks = new array<int>();
		m_PendingFinishSeen = new array<int>();
		m_PendingFinishAgeMs = new array<float>();
		m_CensusCaptureStartMs = 0.0;
		m_CensusLeaseAgeStartMs = 0.0;
		m_CaptureFailed = false;
		m_CaptureFailReason = "";
		m_CaptureFailJobId = "";
		m_LastApplyRetainedSkipped = 0;
		m_PurgeAuthPersIds = new array<string>();
		m_PurgeAuthClasses = new array<string>();
		m_PurgeResolved = new array<int>();
		m_PurgeJobId = "";
		m_PurgeDirectorUid = "";
		m_PurgeConfirmPersId = "";
		m_PurgeConfirmClass = "";
		m_PurgeConfirmNetId = "";
		m_PurgeConfirmParentPersId = "";
		m_PurgeConfirmParentNetId = "";
		m_PurgeConfirmEmitTick = 0.0;
		m_PurgePreN = 0;

		InitSentinelClasses();
		InitCensusColumns();
	}

	protected void InitSentinelClasses()
	{
		m_SentinelClasses.Insert("Barrel_Green");
		m_SentinelClasses.Insert("Barrel_Blue");
		m_SentinelClasses.Insert("Barrel_Red");
		m_SentinelClasses.Insert("Barrel_Yellow");
		m_SentinelClasses.Insert("WoodenCrate");
		m_SentinelClasses.Insert("SeaChest");
		m_SentinelClasses.Insert("FirstAidKit");
		m_SentinelClasses.Insert("StoneKnife");
		m_SentinelClasses.Insert("SewingKit");
		m_SentinelClasses.Insert("OffroadHatchback");
		m_SentinelClasses.Insert("HatchbackWheel");
		m_SentinelClasses.Insert("HatchbackDoors_Driver");
		m_SentinelClasses.Insert("SurvivorM_Mirek");
		m_SentinelClasses.Insert("SurvivorF_Eva");
		m_SentinelClasses.Insert("RadarCap_Black");
		m_SentinelClasses.Insert("RadarCap_Brown");
		m_SentinelClasses.Insert("Armband_Yellow");
		m_SentinelClasses.Insert("Armband_Blue");
		m_SentinelClasses.Insert("WorkingGloves_Beige");
		m_SentinelClasses.Insert("WorkingGloves_Yellow");
		m_SentinelClasses.Insert("WaterBottle");
		m_SentinelClasses.Insert("Compass");
		m_SentinelClasses.Insert("BandageDressing");
		m_SentinelClasses.Insert("OrienteeringCompass");
		m_SentinelClasses.Insert("Fireplace");
	}

	protected void InitCensusColumns()
	{
		m_CensusScol.Insert("class_name");
		m_CensusScol.Insert("loc_kind");
		m_CensusScol.Insert("parent_class");
		m_CensusScol.Insert("parent_net_id");
		m_CensusScol.Insert("slot_name");
		m_CensusScol.Insert("owner_uid");
		m_CensusScol.Insert("own_logical_id");
		m_CensusScol.Insert("net_id");
		m_CensusScol.Insert("pers_id");

		m_CensusNcol.Insert("own_b");
		m_CensusNcol.Insert("in_radius_b");
		m_CensusNcol.Insert("alive_b");
		m_CensusNcol.Insert("ai_agent_b");
		m_CensusNcol.Insert("pos_x_m");
		m_CensusNcol.Insert("pos_y_m");
		m_CensusNcol.Insert("pos_z_m");
		m_CensusNcol.Insert("yaw_deg");
		m_CensusNcol.Insert("pitch_deg");
		m_CensusNcol.Insert("roll_deg");
		m_CensusNcol.Insert("max_hp");
		m_CensusNcol.Insert("health_hp");
		m_CensusNcol.Insert("inv_children_n");
		m_CensusNcol.Insert("spawn_tick_ms");

		// Modo select_all_entityai_b = 1: las mismas columnas mas surface_y_m, la ultima. m_CensusNcol no se toca.
		int ci = 0;
		while (ci < m_CensusNcol.Count())
		{
			m_CensusNcolAll.Insert(m_CensusNcol.Get(ci));
			ci = ci + 1;
		}
		m_CensusNcolAll.Insert("surface_y_m");

		m_WitnessScol.Insert("class_name");
		m_WitnessScol.Insert("net_id");
		m_WitnessScol.Insert("parent_net_id");

		m_WitnessNcol.Insert("sample_idx");
		m_WitnessNcol.Insert("pos_x_m");
		m_WitnessNcol.Insert("pos_y_m");
		m_WitnessNcol.Insert("pos_z_m");
		m_WitnessNcol.Insert("yaw_deg");
		m_WitnessNcol.Insert("tick_ms");
		m_WitnessNcol.Insert("frame");
		m_WitnessNcol.Insert("ai_agent_b");
		m_WitnessNcol.Insert("alive_b");
		m_WitnessNcol.Insert("surface_y_m");
	}

	override void Init(DSBX_QA_Probe probe)
	{
		super.Init(probe);
	}

	override bool Handles(string verb, string role)
	{
		if (role != "server")
			return false;
		if (verb == "per_status")
			return true;
		if (verb == "per_purge_start")
			return true;
		if (verb == "per_apply_scene")
			return true;
		if (verb == "per_reset_scene")
			return true;
		if (verb == "per_child_transition")
			return true;
		if (verb == "per_spawn_raw")
			return true;
		if (verb == "per_census_start")
			return true;
		if (verb == "per_cleanup_qa")
			return true;
		if (verb == "per_witness_start")
			return true;
		return false;
	}

	protected string GetStrArg(DSBX_QA_Args args, string key, string defVal)
	{
		if (!args || !args.sk || !args.sv)
			return defVal;
		int n = args.sk.Count();
		for (int i = 0; i < n; i++)
		{
			if (args.sk.Get(i) == key && i < args.sv.Count())
				return args.sv.Get(i);
		}
		return defVal;
	}

	protected float GetNumArg(DSBX_QA_Args args, string key, float defVal)
	{
		if (!args || !args.nk || !args.nv)
			return defVal;
		int n = args.nk.Count();
		for (int i = 0; i < n; i++)
		{
			if (args.nk.Get(i) == key && i < args.nv.Count())
				return args.nv.Get(i);
		}
		return defVal;
	}

	protected int FindColIdx(array<string> cols, string name)
	{
		if (!cols)
			return -1;
		int n = cols.Count();
		for (int i = 0; i < n; i++)
		{
			if (cols.Get(i) == name)
				return i;
		}
		return -1;
	}

	protected void PutStr(DSBX_QA_Read read, string k, string v)
	{
		read.sk.Insert(k);
		read.sv.Insert(v);
	}

	protected void PutNum(DSBX_QA_Read read, string k, float v)
	{
		read.nk.Insert(k);
		read.nv.Insert(v);
	}

	protected bool HasNumArg(DSBX_QA_Args args, string key)
	{
		if (!args || !args.nk || !args.nv)
			return false;
		int n = args.nk.Count();
		for (int i = 0; i < n; i++)
		{
			if (args.nk.Get(i) == key && i < args.nv.Count())
				return true;
		}
		return false;
	}

	// Entero con signo opcional y de 1 a 10 cifras (ToInt() devuelve 0 con basura y no sirve para validar).
	// string.Get: 1_core/proto/enstring.c:448; ToAscii: enstring.c:86.
	protected bool IsIntStr(string s)
	{
		int n = s.Length();
		if (n < 1)
			return false;
		if (s.Get(0) == "-")
		{
			if (n < 2 || n > 11)
				return false;
		}
		else if (n > 10)
		{
			return false;
		}
		for (int i = 0; i < n; i++)
		{
			int a = s.Get(i).ToAscii();
			if (i == 0 && a == 45 && n > 1)
				continue;
			if (a < 48 || a > 57)
				return false;
		}
		return true;
	}

	// "<high>:<low>", el formato de FormatNetId. IndexOf/Substring: enstring.c:240 y :113.
	protected bool ParseNetIdStr(string s, out int high, out int low)
	{
		high = 0;
		low = 0;
		int sep = s.IndexOf(":");
		if (sep <= 0 || sep >= s.Length() - 1)
			return false;
		string hs = s.Substring(0, sep);
		string ls = s.Substring(sep + 1, s.Length() - sep - 1);
		if (!IsIntStr(hs) || !IsIntStr(ls))
			return false;
		high = hs.ToInt();
		low = ls.ToInt();
		return true;
	}

	protected void EnsurePayloadHas(DSBX_QA_Read read)
	{
		int n = read.has.Count();
		for (int i = 0; i < n; i++)
		{
			if (read.has.Get(i) == "payload")
				return;
		}
		read.has.Insert("payload");
	}

	protected bool IsObjectAlive(Object obj)
	{
		if (!obj)
			return false;
		if (obj.IsPendingDeletion())
			return false;
		EntityAI ent = EntityAI.Cast(obj);
		if (ent && ent.IsSetForDeletion())
			return false;
		return true;
	}

	// Salud de los objetos del mundo, sin excepciones. Object.GetMaxHealth/GetHealth tiran una Virtual Machine Exception
	// en objetos sin sistema de daño (restos de vehiculo del mapa, p. ej. Land_Wreck_Uaz): "No DamageSystemData or not
	// initialized yet". Object.HasDamageSystem() (P:/scripts/3_game/entities/object.c:976) dice si el sistema de daño
	// esta INICIALIZADO, no si el objeto lo tiene. Sin el, max_hp y health_hp valen -1 (centinela: el cable no admite
	// NaN). Lo que crea el QA no pasa por aqui, sino por ReadQaHealth.
	protected void ReadHealth(Object obj, out float maxHp, out float healthHp)
	{
		maxHp = -1.0;
		healthHp = -1.0;
		if (!obj || !obj.HasDamageSystem())
			return;
		maxHp = obj.GetMaxHealth("", "");
		healthHp = obj.GetHealth("", "");
	}

	// Salud de lo que crea el QA: lectura directa, sin la guarda. Sus clases tienen sistema de daño, y GetMaxHealth,
	// GetHealth y SetHealth funcionan ya al crear aunque HasDamageSystem() aun de false: la diag 7 de #22 vio false al
	// crear, y la partida real de S-persist, que lee sin la guarda, dio el control Barrel_Yellow a 1300/1098,5 sin
	// excepciones. Crear con el QA una clase sin sistema de daño no esta soportado (GetMaxHealth tira la excepcion).
	protected void ReadQaHealth(Object obj, out float maxHp, out float healthHp)
	{
		maxHp = -1.0;
		healthHp = -1.0;
		if (!obj)
			return;
		maxHp = obj.GetMaxHealth("", "");
		healthHp = obj.GetHealth("", "");
	}

	// Marca de salud al crear, directa y verificada: SetHealth sin la guarda y relectura. Devuelve 1 si no se pidio marca
	// (ratio <= 0) o si la relectura coincide con max_hp * ratio a 0,01 HP; si no, 0, que el recibo da en health_mark_b:
	// nunca se da por buena una marca sin releerla. maxHp y healthHp salen con la ultima lectura.
	protected int ApplyQaHealthMark(Object obj, float ratio, out float maxHp, out float healthHp)
	{
		ReadQaHealth(obj, maxHp, healthHp);
		if (ratio <= 0.0)
			return 1;
		if (!obj || maxHp <= 0.0)
			return 0;
		obj.SetHealth("", "", maxHp * ratio);
		ReadQaHealth(obj, maxHp, healthHp);
		float diff = healthHp - maxHp * ratio;
		if (Math.AbsFloat(diff) <= 0.01)
			return 1;
		return 0;
	}

	// Lo que crea el QA: lo registrado en esta sesion (escena y raw, con el hijo del control) y las clases centinela, que
	// son las que crea el QA y las que vuelven tras el reinicio sin registro. Su salud se lee directa (ReadQaHealth).
	protected bool IsQaCreated(Object obj)
	{
		if (!obj)
			return false;
		if (FindRecordByObject(obj) != null)
			return true;
		if (FindRawRecordByObject(obj) != null)
			return true;
		return IsSentinelClass(obj.GetType());
	}

	protected string FormatNetId(Object obj)
	{
		if (!obj)
			return "0:0";
		int low = 0;
		int high = 0;
		obj.GetNetworkID(low, high);
		return high.ToString() + ":" + low.ToString();
	}

	protected string FormatPersId(Object obj)
	{
		if (!obj)
			return "0:0:0:0";
		EntityAI ent = EntityAI.Cast(obj);
		if (!ent)
			return "0:0:0:0";
		int b1 = 0;
		int b2 = 0;
		int b3 = 0;
		int b4 = 0;
		ent.GetPersistentID(b1, b2, b3, b4);
		return b1.ToString() + ":" + b2.ToString() + ":" + b3.ToString() + ":" + b4.ToString();
	}

	protected int CountPlayers()
	{
		array<Man> players = new array<Man>();
		g_Game.GetPlayers(players);
		if (!players)
			return 0;
		return players.Count();
	}

	// Resuelve un jugador por PlayerIdentity.GetId(); nunca por players[0].
	protected Man FindPlayerByUid(string wantedUid, out string directorUid, out int presentB, out int aliveB, out int invReadableB, out int invCountN)
	{
		directorUid = wantedUid;
		presentB = 0;
		aliveB = 0;
		invReadableB = 0;
		invCountN = 0;
		if (wantedUid == "")
			return null;
		array<Man> players = new array<Man>();
		g_Game.GetPlayers(players);
		if (!players)
			return null;
		for (int i = 0; i < players.Count(); i++)
		{
			Man cand = players.Get(i);
			if (!cand)
				continue;
			PlayerIdentity ident = cand.GetIdentity();
			if (!ident)
				continue;
			if (ident.GetId() != wantedUid)
				continue;
			presentB = 1;
			if (cand.IsAlive())
				aliveB = 1;
			EntityAI dirEnt = EntityAI.Cast(cand);
			if (dirEnt && dirEnt.GetInventory())
			{
				invReadableB = 1;
				array<EntityAI> items = new array<EntityAI>();
				dirEnt.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, items);
				int cnt = 0;
				for (int j = 0; j < items.Count(); j++)
				{
					if (items.Get(j) != dirEnt)
						cnt = cnt + 1;
				}
				invCountN = cnt;
			}
			return cand;
		}
		return null;
	}

	// t0: sin uid; con un solo jugador listo se devuelve su uid y estado. Con 0 o >=2, uid vacio.
	protected Man FindOnlyPlayer(out string directorUid, out int playersN, out int presentB, out int aliveB, out int invReadableB, out int invCountN)
	{
		directorUid = "";
		playersN = CountPlayers();
		presentB = 0;
		aliveB = 0;
		invReadableB = 0;
		invCountN = 0;
		if (playersN != 1)
			return null;
		array<Man> players = new array<Man>();
		g_Game.GetPlayers(players);
		if (!players || players.Count() != 1)
			return null;
		Man only = players.Get(0);
		if (!only)
			return null;
		PlayerIdentity ident = only.GetIdentity();
		if (ident)
			directorUid = ident.GetId();
		if (directorUid == "")
			return null;
		presentB = 1;
		if (only.IsAlive())
			aliveB = 1;
		EntityAI dirEnt = EntityAI.Cast(only);
		if (dirEnt && dirEnt.GetInventory())
		{
			invReadableB = 1;
			array<EntityAI> items = new array<EntityAI>();
			dirEnt.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, items);
			int cnt = 0;
			for (int j = 0; j < items.Count(); j++)
			{
				if (items.Get(j) != dirEnt)
					cnt = cnt + 1;
			}
			invCountN = cnt;
		}
		return only;
	}

	protected void ReadRealLocation(Object obj, Man director, string directorUid, out string locKind, out string parentClass, out string parentNetId, out string slotName, out string ownerUid, out int invChildrenN, bool proxyAsCargo = false, bool allDescendants = false)
	{
		locKind = "ground";
		parentClass = "";
		parentNetId = "";
		slotName = "";
		ownerUid = "";
		invChildrenN = 0;

		EntityAI ent = EntityAI.Cast(obj);
		if (!ent)
			return;

		if (director && ent.GetHierarchyRootPlayer() == director)
		{
			ownerUid = directorUid;
		}

		GameInventory inv = ent.GetInventory();
		if (inv)
		{
			array<EntityAI> children = new array<EntityAI>();
			inv.EnumerateInventory(InventoryTraversalType.PREORDER, children);
			// inv_children_n: por defecto, los hijos directos, como cuenta el oraculo de S-persist (filas con
			// parent_net_id == net_id, s_persist_eval.py:2290-2306) y el fake; EnumerateInventory PREORDER trae ademas
			// los nietos (la venda del kit dentro del cofre, partida 6). Con allDescendants (censo
			// select_all_entityai_b = 1, contrato de F2) cuenta todos los descendientes, como el fake en ese modo.
			// GetHierarchyParent: entityai.c:885.
			int chCnt = 0;
			for (int i = 0; i < children.Count(); i++)
			{
				EntityAI chEnt = children.Get(i);
				if (chEnt && chEnt != ent && (allDescendants || chEnt.GetHierarchyParent() == ent))
					chCnt = chCnt + 1;
			}
			invChildrenN = chCnt;

			InventoryLocation curLoc = new InventoryLocation();
			if (inv.GetCurrentInventoryLocation(curLoc))
			{
				int locType = curLoc.GetType();
				Object parObj = curLoc.GetParent();
				if (locType == InventoryLocationType.ATTACHMENT && parObj)
				{
					locKind = "attachment";
					parentClass = parObj.GetType();
					parentNetId = FormatNetId(parObj);
					slotName = InventorySlots.GetSlotName(curLoc.GetSlot());
				}
				else if (locType == InventoryLocationType.CARGO && parObj)
				{
					locKind = "cargo";
					parentClass = parObj.GetType();
					parentNetId = FormatNetId(parObj);
					slotName = "Cargo:" + curLoc.GetIdx().ToString() + ":" + curLoc.GetRow().ToString() + ":" + curLoc.GetCol().ToString();
				}
				else if (proxyAsCargo && locType == InventoryLocationType.PROXYCARGO && parObj)
				{
					// Cargo de un objeto grande (edificio): inventorylocation.c:10. Solo en el modo select_all_entityai_b;
					// el modo de S-persist lo sigue viendo como antes. Idx/Row/Col valen tambien en PROXYCARGO (:61-:78).
					locKind = "cargo";
					parentClass = parObj.GetType();
					parentNetId = FormatNetId(parObj);
					slotName = "Cargo:" + curLoc.GetIdx().ToString() + ":" + curLoc.GetRow().ToString() + ":" + curLoc.GetCol().ToString();
				}
				else if (locType == InventoryLocationType.HANDS && parObj)
				{
					locKind = "hands";
					parentClass = parObj.GetType();
					parentNetId = FormatNetId(parObj);
					slotName = "Hands";
				}
			}
		}
	}

	protected int FindSceneIndex(string sceneId)
	{
		int n = m_SceneIds.Count();
		for (int i = 0; i < n; i++)
		{
			if (m_SceneIds.Get(i) == sceneId)
				return i;
		}
		return -1;
	}

	protected void UpsertSceneMeta(string sceneId, int genN, string lastOpId)
	{
		int idx = FindSceneIndex(sceneId);
		if (idx >= 0)
		{
			m_SceneGen.Set(idx, genN);
			m_SceneLastOp.Set(idx, lastOpId);
			return;
		}
		m_SceneIds.Insert(sceneId);
		m_SceneGen.Insert(genN);
		m_SceneLastOp.Insert(lastOpId);
		m_SceneLastRetainedSkipped.Insert(0);
	}

	protected DSBX_QA_PersistRecord FindRecord(string sceneId, string logicalId)
	{
		int n = m_Records.Count();
		for (int i = 0; i < n; i++)
		{
			DSBX_QA_PersistRecord rec = m_Records.Get(i);
			if (rec && rec.m_SceneId == sceneId && rec.m_LogicalId == logicalId)
				return rec;
		}
		return null;
	}

	protected DSBX_QA_PersistRecord FindRecordByObject(Object obj)
	{
		if (!obj)
			return null;
		int n = m_Records.Count();
		for (int i = 0; i < n; i++)
		{
			DSBX_QA_PersistRecord rec = m_Records.Get(i);
			if (rec && rec.m_RefEnt == obj)
				return rec;
		}
		return null;
	}

	// MEN 7: busqueda dentro de la generacion pedida; el padre de una fila
	// nueva puede ser el retenido de la generacion anterior (sin duplicados:
	// cada logical_id tiene como mucho un registro vivo por escena).
	protected DSBX_QA_PersistRecord FindRecordGen(string sceneId, string logicalId, int genN)
	{
		int n = m_Records.Count();
		for (int i = 0; i < n; i++)
		{
			DSBX_QA_PersistRecord rec = m_Records.Get(i);
			if (rec && rec.m_SceneId == sceneId && rec.m_LogicalId == logicalId && rec.m_GenN == genN)
				return rec;
		}
		return null;
	}

	protected DSBX_QA_PersistRecord FindRecordApplyParent(string sceneId, string logicalId, int genN)
	{
		DSBX_QA_PersistRecord rec = FindRecordGen(sceneId, logicalId, genN);
		if (rec)
			return rec;
		int n = m_Records.Count();
		for (int i = 0; i < n; i++)
		{
			DSBX_QA_PersistRecord cand = m_Records.Get(i);
			if (cand && cand.m_SceneId == sceneId && cand.m_LogicalId == logicalId && cand.m_RetainOnReset)
				return cand;
		}
		return null;
	}

	protected DSBX_QA_PersistRawRecord FindRawRecordByObject(Object obj)
	{
		if (!obj)
			return null;
		int n = m_RawRecords.Count();
		for (int i = 0; i < n; i++)
		{
			DSBX_QA_PersistRawRecord raw = m_RawRecords.Get(i);
			if (raw && (raw.m_RefEnt == obj || raw.m_ChildEnt == obj))
				return raw;
		}
		return null;
	}

	// BLOQ 5: descendientes que la limpieza no conoce (ni registro de escena
	// ni registro raw): su presencia protege al contenedor que los lleva.
	protected int CountCleanupForeignDescendants(Object obj)
	{
		EntityAI ent = EntityAI.Cast(obj);
		if (!ent || !ent.GetInventory())
			return 0;
		array<EntityAI> items = new array<EntityAI>();
		ent.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, items);
		int foreignCount = 0;
		for (int i = 0; i < items.Count(); i++)
		{
			EntityAI child = items.Get(i);
			if (!child || child == ent)
				continue;
			if (!FindRecordByObject(child) && !FindRawRecordByObject(child) && !(IsSentinelClass(child.GetType()) && IsQaHealthMark(child)))
				foreignCount = foreignCount + 1;
		}
		return foreignCount;
	}

	protected bool IsValidIdentity(string ident, string zeroValue)
	{
		return ident != "" && ident != zeroValue;
	}

	protected bool IsSentinelClass(string className)
	{
		int n = m_SentinelClasses.Count();
		for (int i = 0; i < n; i++)
		{
			if (m_SentinelClasses.Get(i) == className)
				return true;
		}
		return false;
	}

	protected bool IsInDeletableSet(Object item, string expectEpoch, string sceneId, int targetGenN)
	{
		DSBX_QA_PersistRecord rec = FindRecordByObject(item);
		if (!rec)
			return false;
		if (rec.m_ServerEpoch != expectEpoch)
			return false;
		if (rec.m_SceneId != sceneId)
			return false;
		if (rec.m_GenN != targetGenN)
			return false;
		return true;
	}

	protected int CountForeignDescendants(Object obj, string expectEpoch, string sceneId, int targetGenN)
	{
		EntityAI ent = EntityAI.Cast(obj);
		if (!ent || !ent.GetInventory())
			return 0;
		array<EntityAI> items = new array<EntityAI>();
		ent.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, items);
		int foreignCount = 0;
		for (int i = 0; i < items.Count(); i++)
		{
			EntityAI child = items.Get(i);
			if (!child || child == ent)
				continue;
			if (!IsInDeletableSet(child, expectEpoch, sceneId, targetGenN))
			{
				foreignCount = foreignCount + 1;
			}
		}
		return foreignCount;
	}

	protected int CountForeignDescendantsAnyGen(Object ent, string expectEpoch, string sceneId)
	{
		if (!ent)
			return 0;
		EntityAI e = EntityAI.Cast(ent);
		if (!e || !e.GetInventory())
			return 0;
		array<EntityAI> items = new array<EntityAI>();
		e.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, items);
		int foreignCount = 0;
		for (int i = 0; i < items.Count(); i++)
		{
			EntityAI child = items.Get(i);
			if (!child || child == e)
				continue;
			DSBX_QA_PersistRecord childRec = FindRecordByObject(child);
			bool deletable = childRec && childRec.m_SceneId == sceneId && childRec.m_ServerEpoch == expectEpoch;
			if (!deletable)
				foreignCount = foreignCount + 1;
		}
		return foreignCount;
	}

	// MEN 8: False si el lease caduca a mitad; cada borrado va guardado y la
	// caducidad se propaga como error, nunca como exito parcial silencioso.
	protected bool ReapplyResetWithRetention(string sceneId, string expectEpoch)
	{
		for (int i = 0; i < m_Records.Count(); i++)
		{
			DSBX_QA_PersistRecord rec = m_Records.Get(i);
			if (rec && rec.m_SceneId == sceneId && rec.m_ServerEpoch == expectEpoch)
			{
				rec.m_RetainOnReset = false;
				rec.m_ForeignDescendantsN = 0;
			}
		}
		for (int j = 0; j < m_Records.Count(); j++)
		{
			DSBX_QA_PersistRecord cand = m_Records.Get(j);
			if (!cand || cand.m_SceneId != sceneId || cand.m_ServerEpoch != expectEpoch || !cand.m_RefEnt)
				continue;
			int fCnt = CountForeignDescendantsAnyGen(cand.m_RefEnt, expectEpoch, sceneId);
			if (fCnt > 0)
			{
				cand.m_RetainOnReset = true;
				cand.m_ForeignDescendantsN = fCnt;
				EntityAI curEnt = EntityAI.Cast(cand.m_RefEnt);
				while (curEnt)
				{
					EntityAI anc = curEnt.GetHierarchyParent();
					if (!anc)
						break;
					DSBX_QA_PersistRecord ancRec = FindRecordByObject(anc);
					if (ancRec && ancRec.m_SceneId == sceneId && ancRec.m_ServerEpoch == expectEpoch)
					{
						ancRec.m_RetainOnReset = true;
						if (ancRec.m_ForeignDescendantsN < fCnt)
							ancRec.m_ForeignDescendantsN = fCnt;
					}
					curEnt = anc;
				}
			}
		}
		for (int p1 = m_Records.Count() - 1; p1 >= 0; p1--)
		{
			DSBX_QA_PersistRecord childRec = m_Records.Get(p1);
			if (!childRec || childRec.m_SceneId != sceneId || childRec.m_ServerEpoch != expectEpoch)
				continue;
			if (childRec.m_ParentId == "" || childRec.m_RetainOnReset)
				continue;
			if (!m_Probe.LeaseOk())
				return false;
			if (IsObjectAlive(childRec.m_RefEnt))
				g_Game.ObjectDelete(childRec.m_RefEnt);
			childRec.m_RefEnt = null;
			m_Records.RemoveOrdered(p1);
		}
		for (int p2 = m_Records.Count() - 1; p2 >= 0; p2--)
		{
			DSBX_QA_PersistRecord rootRec = m_Records.Get(p2);
			if (!rootRec || rootRec.m_SceneId != sceneId || rootRec.m_ServerEpoch != expectEpoch)
				continue;
			if (rootRec.m_ParentId != "" || rootRec.m_RetainOnReset)
				continue;
			if (!m_Probe.LeaseOk())
				return false;
			if (IsObjectAlive(rootRec.m_RefEnt))
				g_Game.ObjectDelete(rootRec.m_RefEnt);
			rootRec.m_RefEnt = null;
			m_Records.RemoveOrdered(p2);
		}
		return true;
	}

	override void OnStartOp(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string verb = op.verb;
		if (verb == "per_cleanup_qa")
		{
			HandleCleanupQA(op, args, res);
			return;
		}

		// per_status solo observa (sin efecto): legible aun con lease caducado, como el fake.
		if (verb == "per_status" && m_Probe)
		{
			HandleStatus(op, args, res);
			return;
		}

		// LeaseOk: DSBX_QA_Probe.c:447; guarda de entrada y antes de cada efecto (E1).
		if (!m_Probe || !m_Probe.LeaseOk())
		{
			res.status = "error";
			res.reason = "lease_expired";
			return;
		}
		if (verb == "per_apply_scene")
		{
			HandleApplyScene(op, args, res);
			return;
		}
		if (verb == "per_reset_scene")
		{
			HandleResetScene(op, args, res);
			return;
		}
		if (verb == "per_child_transition")
		{
			HandleChildTransition(op, args, res);
			return;
		}
		if (verb == "per_spawn_raw")
		{
			HandleSpawnRaw(op, args, res);
			return;
		}
		if (verb == "per_purge_start")
		{
			HandlePurgeStart(op, args, res);
			return;
		}
		if (verb == "per_census_start")
		{
			HandleCensusStart(op, args, res);
			return;
		}
		if (verb == "per_witness_start")
		{
			HandleWitnessStart(op, args, res);
			return;
		}

		res.status = "error";
		res.reason = "unknown_verb";
	}

	protected void HandleStatus(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string wantedUid = GetStrArg(args, "director_uid", "");
		string directorUid = "";
		int playersN = 0;
		int presentB = 0;
		int aliveB = 0;
		int invReadableB = 0;
		int invCountN = 0;
		if (wantedUid == "")
		{
			FindOnlyPlayer(directorUid, playersN, presentB, aliveB, invReadableB, invCountN);
		}
		else
		{
			FindPlayerByUid(wantedUid, directorUid, presentB, aliveB, invReadableB, invCountN);
			playersN = CountPlayers();
		}

		res.status = "done";
		EnsurePayloadHas(res.read);
		PutStr(res.read, "server_epoch", m_Probe.GetInst());
		PutStr(res.read, "director_uid", directorUid);

		PutNum(res.read, "players_n", (float)playersN);
		PutNum(res.read, "tick_ms", m_Probe.NowMs());
		PutNum(res.read, "frame", m_Probe.m_Frame);
		PutNum(res.read, "registered_total_n", m_Records.Count());
		PutNum(res.read, "scenes_count_n", m_SceneIds.Count());
		PutNum(res.read, "director_present_b", presentB);
		PutNum(res.read, "director_alive_b", aliveB);
		PutNum(res.read, "director_inv_readable_b", invReadableB);
		PutNum(res.read, "director_inv_count_n", invCountN);

		res.read.scol.Insert("scene_id");
		res.read.scol.Insert("last_op_id");
		res.read.ncol.Insert("gen_n");
		res.read.ncol.Insert("own_alive_n");

		int scCount = m_SceneIds.Count();
		res.read.rows = scCount;
		for (int i = 0; i < scCount; i++)
		{
			string sid = m_SceneIds.Get(i);
			int genN = m_SceneGen.Get(i);
			string lastOp = m_SceneLastOp.Get(i);
			int aliveN = 0;
			for (int j = 0; j < m_Records.Count(); j++)
			{
				DSBX_QA_PersistRecord r = m_Records.Get(j);
				if (r && r.m_SceneId == sid && r.m_GenN == genN && IsObjectAlive(r.m_RefEnt))
				{
					aliveN = aliveN + 1;
				}
			}
			res.read.scell.Insert(sid);
			res.read.scell.Insert(lastOp);
			res.read.ncell.Insert(genN);
			res.read.ncell.Insert(aliveN);
		}
	}

	// "<b1>:<b2>:<b3>:<b4>" con cuatro enteros; no vale "0:0:0:0".
	protected bool IsPersIdStr(string s)
	{
		if (s == "" || s == "0:0:0:0")
			return false;
		int sep1 = s.IndexOf(":");
		if (sep1 <= 0 || sep1 >= s.Length() - 1)
			return false;
		string p1 = s.Substring(0, sep1);
		string rest1 = s.Substring(sep1 + 1, s.Length() - sep1 - 1);
		int sep2 = rest1.IndexOf(":");
		if (sep2 <= 0 || sep2 >= rest1.Length() - 1)
			return false;
		string p2 = rest1.Substring(0, sep2);
		string rest2 = rest1.Substring(sep2 + 1, rest1.Length() - sep2 - 1);
		int sep3 = rest2.IndexOf(":");
		if (sep3 <= 0 || sep3 >= rest2.Length() - 1)
			return false;
		string p3 = rest2.Substring(0, sep3);
		string p4 = rest2.Substring(sep3 + 1, rest2.Length() - sep3 - 1);
		if (!IsIntStr(p1) || !IsIntStr(p2) || !IsIntStr(p3) || !IsIntStr(p4))
			return false;
		return true;
	}

	protected int FindPurgeAuthIndex(string persId)
	{
		int n = m_PurgeAuthPersIds.Count();
		for (int i = 0; i < n; i++)
		{
			if (m_PurgeAuthPersIds.Get(i) == persId)
				return i;
		}
		return -1;
	}

	protected int CountPersIdInTree(array<EntityAI> items, string persId)
	{
		int count = 0;
		for (int i = 0; i < items.Count(); i++)
		{
			EntityAI ent = items.Get(i);
			if (ent && IsObjectAlive(ent) && FormatPersId(ent) == persId)
				count = count + 1;
		}
		return count;
	}

	protected EntityAI FindFirstPersIdInTree(array<EntityAI> items, string persId)
	{
		for (int i = 0; i < items.Count(); i++)
		{
			EntityAI ent = items.Get(i);
			if (ent && IsObjectAlive(ent) && FormatPersId(ent) == persId)
				return ent;
		}
		return null;
	}

	protected int PurgeDepthOf(EntityAI ent, Man director)
	{
		int depth = 0;
		EntityAI cur = ent;
		while (cur && cur != director)
		{
			depth = depth + 1;
			EntityAI parent = cur.GetHierarchyParent();
			if (!parent)
				break;
			cur = parent;
		}
		return depth;
	}

	protected string ParentPersIdOf(EntityAI ent)
	{
		if (!ent)
			return "0:0:0:0";
		EntityAI parent = ent.GetHierarchyParent();
		if (!parent)
			return "0:0:0:0";
		return FormatPersId(parent);
	}

	protected string ParentNetIdOf(EntityAI ent)
	{
		if (!ent)
			return "";
		EntityAI parent = ent.GetHierarchyParent();
		if (!parent)
			return "";
		return FormatNetId(parent);
	}

	protected void CollectPurgeSubtree(EntityAI cand, array<EntityAI> outItems)
	{
		if (!cand)
			return;
		outItems.Insert(cand);
		if (!cand.GetInventory())
			return;
		array<EntityAI> kids = new array<EntityAI>();
		cand.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, kids);
		for (int i = 0; i < kids.Count(); i++)
		{
			EntityAI k = kids.Get(i);
			if (k && k != cand)
				outItems.Insert(k);
		}
	}

	protected bool IsPurgeTreeEligible(EntityAI cand, Man director, array<EntityAI> treeItems)
	{
		if (!cand || !director)
			return false;
		if (cand.GetHierarchyRootPlayer() != director)
			return false;
		string candPers = FormatPersId(cand);
		if (!IsPersIdStr(candPers))
			return false;
		int candIdx = FindPurgeAuthIndex(candPers);
		if (candIdx < 0)
			return false;
		if (m_PurgeAuthClasses.Get(candIdx) != cand.GetType())
			return false;
		if (CountPersIdInTree(treeItems, candPers) != 1)
			return false;
		array<EntityAI> sub = new array<EntityAI>();
		CollectPurgeSubtree(cand, sub);
		for (int i = 0; i < sub.Count(); i++)
		{
			EntityAI d = sub.Get(i);
			if (!d)
				return false;
			string dp = FormatPersId(d);
			if (!IsPersIdStr(dp))
				return false;
			int di = FindPurgeAuthIndex(dp);
			if (di < 0)
				return false;
			if (m_PurgeAuthClasses.Get(di) != d.GetType())
				return false;
			if (CountPersIdInTree(treeItems, dp) != 1)
				return false;
			if (d.GetHierarchyRootPlayer() != director)
				return false;
		}
		return true;
	}

	protected EntityAI PickPurgeLeaf(EntityAI cand, Man director, array<EntityAI> treeItems)
	{
		array<EntityAI> sub = new array<EntityAI>();
		CollectPurgeSubtree(cand, sub);
		EntityAI best = null;
		int bestDepth = -1;
		for (int i = 0; i < sub.Count(); i++)
		{
			EntityAI d = sub.Get(i);
			if (!d)
				continue;
			bool hasChild = false;
			for (int j = 0; j < treeItems.Count(); j++)
			{
				EntityAI other = treeItems.Get(j);
				if (other && other != d && other.GetHierarchyParent() == d)
				{
					hasChild = true;
					break;
				}
			}
			if (hasChild)
				continue;
			int depth = PurgeDepthOf(d, director);
			if (depth > bestDepth)
			{
				bestDepth = depth;
				best = d;
			}
		}
		return best;
	}

	protected bool AppendPurgeRow(string phase, string persId, string className, string parentPersId, string parentNetId, string ownerUid, string result, string netId, int depthN, float emitTick, float leaseAge, float leaseLimit, float maxHp, float healthHp, float confirmTick)
	{
		array<string> svals = new array<string>();
		svals.Insert(phase);
		svals.Insert(persId);
		svals.Insert(className);
		svals.Insert(parentPersId);
		svals.Insert(ownerUid);
		svals.Insert(result);
		svals.Insert(netId);
		svals.Insert(parentNetId);
		array<float> nvals = new array<float>();
		nvals.Insert((float)depthN);
		nvals.Insert(emitTick);
		nvals.Insert(leaseAge);
		nvals.Insert(leaseLimit);
		nvals.Insert(maxHp);
		nvals.Insert(healthHp);
		nvals.Insert(confirmTick);
		return m_Jobs.AppendRow(m_PurgeJobId, nvals, svals);
	}

	// MENOR 15: el nacimiento en el inventario se exige a todo registro del subarbol
	// cuyo destino sea un jugador, no solo a la raiz que se mueve.
	protected bool SubtreeBornInInventory(EntityAI root)
	{
		if (!root)
			return false;
		DSBX_QA_PersistRecord rootRec = FindRecordByObject(root);
		if (!rootRec || rootRec.m_BornInInventory != 1)
			return false;
		if (!root.GetInventory())
			return true;
		array<EntityAI> sub = new array<EntityAI>();
		root.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, sub);
		for (int i = 0; i < sub.Count(); i++)
		{
			EntityAI se = sub.Get(i);
			if (!se || se == root)
				continue;
			DSBX_QA_PersistRecord seRec = FindRecordByObject(se);
			if (seRec && seRec.m_BornInInventory != 1)
				return false;
		}
		return true;
	}

	protected void AppendPurgeTreeRow(string phase, EntityAI ent, Man director, string directorUid, string result, int depthN, float emitTick, float leaseAge, float leaseLimit)
	{
		float maxHp = -1.0;
		float healthHp = -1.0;
		// MENOR 7: lo vanilla del director se lee como el censo (ReadHealth); lo del QA, con ReadQaHealth.
		if (IsQaCreated(ent)) ReadQaHealth(ent, maxHp, healthHp); else ReadHealth(ent, maxHp, healthHp);
		// MENOR 13: owner_uid medido por la raiz del arbol, no una constante de la orden.
		string rowOwnerUid = "";
		if (director && ent.GetHierarchyRootPlayer() == director) rowOwnerUid = directorUid;
		AppendPurgeRow(phase, FormatPersId(ent), ent.GetType(), ParentPersIdOf(ent), ParentNetIdOf(ent), rowOwnerUid, result, FormatNetId(ent), depthN, emitTick, leaseAge, leaseLimit, maxHp, healthHp, 0.0);
	}

	protected void HandlePurgeStart(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string expectEpoch = GetStrArg(args, "expect_epoch", "");
		string directorUidArg = GetStrArg(args, "director_uid", "");
		if (expectEpoch != m_Probe.GetInst())
		{
			PersistReject(res, "rejected", "stale_epoch");
			return;
		}
		int rows = 0;
		if (args && args.rows > 0)
			rows = args.rows;
		if (rows < 1 || rows > 16)
		{
			PersistReject(res, "rejected", "bad_args");
			return;
		}
		int idxPers = FindColIdx(args.scol, "pers_id");
		int idxClass = FindColIdx(args.scol, "class_name");
		if (idxPers < 0 || idxClass < 0)
		{
			PersistReject(res, "rejected", "bad_args");
			return;
		}
		int scolCount = args.scol.Count();
		array<string> authPers = new array<string>();
		array<string> authClass = new array<string>();
		for (int r = 0; r < rows; r++)
		{
			int base = r * scolCount;
			string pid = args.scell.Get(base + idxPers);
			string cname = args.scell.Get(base + idxClass);
			if (!IsPersIdStr(pid) || cname == "")
			{
				PersistReject(res, "rejected", "bad_args");
				return;
			}
			for (int q = 0; q < authPers.Count(); q++)
			{
				if (authPers.Get(q) == pid)
				{
					PersistReject(res, "rejected", "bad_args");
					return;
				}
			}
			authPers.Insert(pid);
			authClass.Insert(cname);
		}
		string resolvedUid = directorUidArg;
		int presentB = 0;
		int aliveB = 0;
		int invReadableB = 0;
		int invCountN = 0;
		Man director = FindPlayerByUid(directorUidArg, resolvedUid, presentB, aliveB, invReadableB, invCountN);
		if (!director || presentB != 1 || aliveB != 1 || invReadableB != 1)
		{
			PersistReject(res, "rejected", "director_not_ready");
			return;
		}
		array<string> ncol = new array<string>();
		ncol.Insert("depth_n");
		ncol.Insert("emit_tick_ms");
		ncol.Insert("lease_age_ms");
		ncol.Insert("lease_limit_ms");
		ncol.Insert("max_hp");
		ncol.Insert("health_hp");
		// Aclaracion 2: columna nueva al final; las anteriores no cambian.
		ncol.Insert("confirm_tick_ms");
		array<string> scol = new array<string>();
		scol.Insert("phase");
		scol.Insert("pers_id");
		scol.Insert("class_name");
		scol.Insert("parent_pers_id");
		scol.Insert("owner_uid");
		scol.Insert("result");
		scol.Insert("net_id");
		scol.Insert("parent_net_id");
		string err = m_Jobs.StartJob(this, op.op_id, "per_purge", ncol, scol, 8, 256, PURGE_MAX_DURATION_MS, "stop");
		if (err != "")
		{
			PersistReject(res, "rejected", err);
			return;
		}
		m_PurgeJobId = op.op_id;
		m_PurgeDirectorUid = directorUidArg;
		m_PurgeAuthPersIds = authPers;
		m_PurgeAuthClasses = authClass;
		m_PurgeResolved = new array<int>();
		for (int z = 0; z < authPers.Count(); z++)
			m_PurgeResolved.Insert(0);
		m_PurgeConfirmPersId = "";
		m_PurgeConfirmClass = "";
		m_PurgeConfirmNetId = "";
		m_PurgeConfirmParentPersId = "";
		m_PurgeConfirmParentNetId = "";
		EntityAI dirEnt = EntityAI.Cast(director);
		array<EntityAI> treeItems = new array<EntityAI>();
		if (dirEnt && dirEnt.GetInventory())
			dirEnt.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, treeItems);
		int preN = 0;
		for (int t = 0; t < treeItems.Count(); t++)
		{
			EntityAI te = treeItems.Get(t);
			if (te && te != dirEnt && IsObjectAlive(te))
				preN = preN + 1;
		}
		m_PurgePreN = preN;
		if (preN + authPers.Count() > 256)
		{
			m_Jobs.EndJob(m_PurgeJobId, "failed", "rows_cap");
		}
		else
		{
			for (int p = 0; p < treeItems.Count(); p++)
			{
				EntityAI pe = treeItems.Get(p);
				if (!pe || pe == dirEnt || !IsObjectAlive(pe))
					continue;
				AppendPurgeTreeRow("pre", pe, director, directorUidArg, "", PurgeDepthOf(pe, director), 0.0, 0.0, 0.0);
				if (m_Jobs.GetState(m_PurgeJobId) != "running")
					break;
			}
		}
		res.status = "done";
		m_Jobs.FillStartRead(res.read, op.op_id, "per_purge");
		// MENOR 14: el acuse publica el estado real del trabajo (p. ej. failed/rows_cap), no "running" fijo.
		string ackState = m_Jobs.GetState(m_PurgeJobId);
		if (ackState != "" && res.read.sv.Count() > 1)
			res.read.sv.Set(1, ackState);
		PutNum(res.read, "pre_n", (float)preN);
	}

	protected bool PurgeAllResolved()
	{
		for (int i = 0; i < m_PurgeResolved.Count(); i++)
		{
			if (m_PurgeResolved.Get(i) == 0)
				return false;
		}
		return true;
	}

	protected void ResolvePurgeResult(int idx, string result, string persId, string className, string parentPersId, string parentNetId, string netId, string ownerUid, float confirmTick)
	{
		if (idx < 0)
			return;
		if (m_PurgeResolved.Get(idx) != 0)
			return;
		bool ok = AppendPurgeRow("result", persId, className, parentPersId, parentNetId, ownerUid, result, netId, 0, 0.0, 0.0, 0.0, -1.0, -1.0, confirmTick);
		if (!ok)
			return;
		m_PurgeResolved.Set(idx, 1);
	}

	protected void TickPurge()
	{
		if (m_PurgeJobId == "")
			return;
		if (m_Jobs.GetState(m_PurgeJobId) != "running")
			return;
		string resolvedUid = m_PurgeDirectorUid;
		int presentB = 0;
		int aliveB = 0;
		int invReadableB = 0;
		int invCountN = 0;
		Man director = FindPlayerByUid(m_PurgeDirectorUid, resolvedUid, presentB, aliveB, invReadableB, invCountN);
		if (!director || presentB != 1 || aliveB != 1 || invReadableB != 1)
		{
			m_Jobs.EndJob(m_PurgeJobId, "failed", "director_lost");
			return;
		}
		EntityAI dirEnt = EntityAI.Cast(director);
		array<EntityAI> treeItems = new array<EntityAI>();
		if (dirEnt && dirEnt.GetInventory())
			dirEnt.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, treeItems);
		if (m_PurgeConfirmPersId != "")
		{
			int still = CountPersIdInTree(treeItems, m_PurgeConfirmPersId);
			if (still > 0)
				return;
			int cidx = FindPurgeAuthIndex(m_PurgeConfirmPersId);
			// Aclaracion 2: el tick en que se confirma que ya no esta; posterior a su emit_tick_ms.
			float confirmTick = m_Probe.NowMs();
			if (confirmTick <= m_PurgeConfirmEmitTick)
				confirmTick = m_PurgeConfirmEmitTick + 1.0;
			ResolvePurgeResult(cidx, "deleted", m_PurgeConfirmPersId, m_PurgeConfirmClass, m_PurgeConfirmParentPersId, m_PurgeConfirmParentNetId, m_PurgeConfirmNetId, m_PurgeDirectorUid, confirmTick);
			m_PurgeConfirmPersId = "";
			m_PurgeConfirmClass = "";
			m_PurgeConfirmNetId = "";
			m_PurgeConfirmParentPersId = "";
			m_PurgeConfirmParentNetId = "";
			if (m_Jobs.GetState(m_PurgeJobId) != "running")
				return;
		}
		if (PurgeAllResolved())
		{
			m_Jobs.EndJob(m_PurgeJobId, "done", "ok");
			return;
		}
		for (int a = 0; a < m_PurgeAuthPersIds.Count(); a++)
		{
			if (m_Jobs.GetState(m_PurgeJobId) != "running")
				return;
			if (m_PurgeResolved.Get(a) != 0)
				continue;
			string pid = m_PurgeAuthPersIds.Get(a);
			string cls = m_PurgeAuthClasses.Get(a);
			int count = CountPersIdInTree(treeItems, pid);
			if (count == 0)
			{
				ResolvePurgeResult(a, "absent", pid, cls, "", "", "", "", 0.0);
				continue;
			}
			if (count > 1)
			{
				EntityAI first = FindFirstPersIdInTree(treeItems, pid);
				string firstOwner = "";
				if (first && director && first.GetHierarchyRootPlayer() == director) firstOwner = m_PurgeDirectorUid;
				ResolvePurgeResult(a, "ambiguous", pid, cls, ParentPersIdOf(first), ParentNetIdOf(first), FormatNetId(first), firstOwner, 0.0);
				continue;
			}
			EntityAI cand = FindFirstPersIdInTree(treeItems, pid);
			// MENOR 12: el propio director nunca es candidato.
			if (!cand || cand == dirEnt || cand.IsMan() || cand.GetType() != cls || !IsPurgeTreeEligible(cand, director, treeItems))
			{
				string candOwner = "";
				if (cand && director && cand.GetHierarchyRootPlayer() == director) candOwner = m_PurgeDirectorUid;
				ResolvePurgeResult(a, "retained_foreign", pid, cls, ParentPersIdOf(cand), ParentNetIdOf(cand), FormatNetId(cand), candOwner, 0.0);
				continue;
			}
			EntityAI leaf = PickPurgeLeaf(cand, director, treeItems);
			if (!leaf)
			{
				string candOwner2 = "";
				if (cand && director && cand.GetHierarchyRootPlayer() == director) candOwner2 = m_PurgeDirectorUid;
				ResolvePurgeResult(a, "retained_foreign", pid, cls, ParentPersIdOf(cand), ParentNetIdOf(cand), FormatNetId(cand), candOwner2, 0.0);
				continue;
			}
			if (!m_Probe.LeaseOk())
				return;
			float emitTick = m_Probe.NowMs();
			int leaseAge = (int)m_Probe.LeaseAgeMs();
			int leaseLimit = m_Probe.GetLeaseMs();
			array<EntityAI> leafSub = new array<EntityAI>();
			CollectPurgeSubtree(leaf, leafSub);
			for (int s = 0; s < leafSub.Count(); s++)
			{
				EntityAI se = leafSub.Get(s);
				if (!se || !IsObjectAlive(se))
					continue;
				AppendPurgeTreeRow("emit", se, director, m_PurgeDirectorUid, "", PurgeDepthOf(se, director), emitTick, (float)leaseAge, (float)leaseLimit);
				if (m_Jobs.GetState(m_PurgeJobId) != "running")
					return;
			}
			string leafPers = FormatPersId(leaf);
			string leafClass = leaf.GetType();
			string leafNet = FormatNetId(leaf);
			string leafParentPers = ParentPersIdOf(leaf);
			string leafParentNet = ParentNetIdOf(leaf);
			g_Game.ObjectDelete(leaf);
			m_PurgeConfirmPersId = leafPers;
			m_PurgeConfirmClass = leafClass;
			m_PurgeConfirmNetId = leafNet;
			m_PurgeConfirmParentPersId = leafParentPers;
			m_PurgeConfirmParentNetId = leafParentNet;
			m_PurgeConfirmEmitTick = emitTick;
			return;
		}
		if (PurgeAllResolved())
			m_Jobs.EndJob(m_PurgeJobId, "done", "ok");
	}

	protected void EmitApplyResponse(DSBX_QA_Read read, string sceneId, string sceneOpId, string pathway, int genN, int idempotentHitB)
	{
		EnsurePayloadHas(read);
		read.scol.Insert("logical_id");
		read.scol.Insert("class_name");
		read.scol.Insert("net_id");
		read.scol.Insert("obs_loc_kind");
		read.scol.Insert("obs_parent_net_id");
		read.scol.Insert("obs_slot_name");

		read.ncol.Insert("ok_b");
		read.ncol.Insert("alive_b");
		read.ncol.Insert("ai_agent_b");
		read.ncol.Insert("req_y_m");
		read.ncol.Insert("q9_x_m");
		read.ncol.Insert("q9_y_m");
		read.ncol.Insert("q9_z_m");
		read.ncol.Insert("q9_dx_m");
		read.ncol.Insert("q9_dy_m");
		read.ncol.Insert("q9_dz_m");
		read.ncol.Insert("q9_err_3d_m");
		read.ncol.Insert("q9_yaw_deg");
		read.ncol.Insert("q9_pitch_deg");
		read.ncol.Insert("q9_roll_deg");
		read.ncol.Insert("max_hp");
		read.ncol.Insert("health_hp");
		read.ncol.Insert("spawn_tick_ms");
		read.ncol.Insert("health_mark_b");

		int rootsN = 0;
		int childrenN = 0;
		int rowCount = 0;
		int okCount = 0;
		for (int i = 0; i < m_Records.Count(); i++)
		{
			DSBX_QA_PersistRecord r = m_Records.Get(i);
			if (!r || r.m_SceneId != sceneId || r.m_GenN != genN)
				continue;
			rowCount = rowCount + 1;
			if (r.m_OkB == 1)
			{
				okCount = okCount + 1;
				if (r.m_ParentId == "")
					rootsN = rootsN + 1;
				else
					childrenN = childrenN + 1;
			}

			read.scell.Insert(r.m_LogicalId);
			read.scell.Insert(r.m_ClassName);
			read.scell.Insert(r.m_NetId);
			read.scell.Insert(r.m_ObsLocKind);
			read.scell.Insert(r.m_ObsParentNetId);
			read.scell.Insert(r.m_ObsSlotName);

			read.ncell.Insert(r.m_OkB);
			read.ncell.Insert(r.m_AliveB);
			read.ncell.Insert(r.m_AiAgentB);
			read.ncell.Insert(r.m_ReqYM);
			read.ncell.Insert(r.m_Q9XM);
			read.ncell.Insert(r.m_Q9YM);
			read.ncell.Insert(r.m_Q9ZM);
			read.ncell.Insert(r.m_Q9DxM);
			read.ncell.Insert(r.m_Q9DyM);
			read.ncell.Insert(r.m_Q9DzM);
			read.ncell.Insert(r.m_Q9Err3dM);
			read.ncell.Insert(r.m_Q9YawDeg);
			read.ncell.Insert(r.m_Q9PitchDeg);
			read.ncell.Insert(r.m_Q9RollDeg);
			read.ncell.Insert(r.m_MaxHp);
			read.ncell.Insert(r.m_HealthHp);
			read.ncell.Insert(r.m_SpawnTickMs);
			read.ncell.Insert(r.m_HealthMarkB);
		}
		read.rows = rowCount;

		string applyStatus = "ok";
		string applyReason = "";
		if (okCount == 0)
		{
			applyStatus = "failed";
			applyReason = "creation_failed";
		}
		else if (okCount < rowCount)
		{
			applyStatus = "partial";
			applyReason = "creation_failed";
		}
		// MEN 7: filas retenidas de la generacion anterior -> parcial explicito.
		if (m_LastApplyRetainedSkipped > 0)
		{
			applyReason = "retained_prior_generation";
			if (okCount == 0)
				applyStatus = "failed";
			else
				applyStatus = "partial";
		}
		PutStr(read, "apply_status", applyStatus);
		PutStr(read, "reason", applyReason);
		PutStr(read, "server_epoch", m_Probe.GetInst());
		PutStr(read, "scene_id", sceneId);
		PutStr(read, "scene_op_id", sceneOpId);
		PutStr(read, "q9_pathway", pathway);

		PutNum(read, "gen_n", genN);
		PutNum(read, "retained_skipped_n", m_LastApplyRetainedSkipped);
		PutNum(read, "created_roots_n", rootsN);
		PutNum(read, "created_children_n", childrenN);
		PutNum(read, "idempotent_hit_b", idempotentHitB);
		PutNum(read, "q9_tick_ms", m_Probe.NowMs());
		PutNum(read, "q9_frame", m_Probe.m_Frame);
	}

	protected void PersistReject(DSBX_QA_Result target, string state, string why)
	{
		target.status = state;
		target.reason = why;
	}

	protected Object PersistSpawnRootAt(string kind, vector where, float yaw, string category, string pathway, bool stripNoPersist)
	{
		int flags = FLAGS_STATIC;
		bool creature = false;
		if (category == "infected")
			creature = true;
		if (category == "animal")
			creature = true;
		if (creature && pathway == "a")
			flags = FLAGS_AI_A;
		if (creature && pathway != "a")
			flags = FLAGS_AI_B;
		if (stripNoPersist)
			flags = flags & (~FLAG_ECE_NOPERSISTENCY_WORLD);
		Object made = g_Game.CreateObjectEx(kind, where, flags, FLAG_RF_DEFAULT);
		if (made)
			made.SetPosition(where);
		if (made)
			made.SetOrientation(Vector(yaw, 0.0, 0.0));
		return made;
	}

	protected Object PersistCreateDirectInInventory(EntityAI holder, string kind, string slot, bool stripNoPersist)
	{
		int flags = FLAGS_INV_OWN;
		if (stripNoPersist)
			flags = flags & (~FLAG_ECE_NOPERSISTENCY_WORLD);
		InventoryLocation spot = new InventoryLocation();
		bool spotReady = false;
		int slotNumber = -1;
		if (slot != "Cargo")
			slotNumber = InventorySlots.GetSlotIdFromString(slot);
		if (slot == "Cargo")
			spotReady = holder.GetInventory().FindFirstFreeLocationForNewEntity(kind, FindInventoryLocationType.CARGO, spot);
		if (slot != "Cargo" && InventorySlots.IsSlotIdValid(slotNumber) && holder.GetInventory().HasAttachmentSlot(slotNumber) && holder.GetInventory().FindAttachment(slotNumber) == null)
		{
			spot.SetAttachment(holder, null, slotNumber);
			spotReady = true;
		}
		Object made = null;
		if (spotReady)
			made = GameInventory.LocationCreateEntity(spot, kind, flags, FLAG_RF_DEFAULT);
		return made;
	}

	protected Object PersistCreateByMovingIn(EntityAI holder, string kind, string slot, bool stripNoPersist)
	{
		int flags = FLAGS_STATIC;
		if (stripNoPersist)
			flags = flags & (~FLAG_ECE_NOPERSISTENCY_WORLD);
		Object candidate = g_Game.CreateObjectEx(kind, holder.GetPosition(), flags, FLAG_RF_DEFAULT);
		EntityAI candidateEnt = EntityAI.Cast(candidate);
		bool moved = false;
		InventoryLocation fromSpot = new InventoryLocation();
		InventoryLocation toSpot = new InventoryLocation();
		bool fromReady = false;
		bool toReady = false;
		int slotNumber = -1;
		if (slot != "Cargo")
			slotNumber = InventorySlots.GetSlotIdFromString(slot);
		if (candidateEnt && candidateEnt.GetInventory())
			fromReady = candidateEnt.GetInventory().GetCurrentInventoryLocation(fromSpot);
		if (slot == "Cargo" && candidateEnt)
			toReady = holder.GetInventory().FindFreeLocationFor(candidateEnt, FindInventoryLocationType.CARGO, toSpot);
		if (slot != "Cargo" && InventorySlots.IsSlotIdValid(slotNumber) && holder.GetInventory().HasAttachmentSlot(slotNumber) && holder.GetInventory().FindAttachment(slotNumber) == null)
		{
			toSpot.SetAttachment(holder, candidateEnt, slotNumber);
			toReady = true;
		}
		if (fromReady && toReady && GameInventory.LocationCanMoveEntity(fromSpot, toSpot))
			moved = GameInventory.LocationSyncMoveEntity(fromSpot, toSpot);
		if (moved)
			return candidate;
		if (candidate)
			g_Game.ObjectDelete(candidate);
		return null;
	}

	protected Object PersistSpawnSceneChild(string scene, string parentLogical, int generation, string kind, string slot, bool stripNoPersist)
	{
		DSBX_QA_PersistRecord parentRecord = FindRecordApplyParent(scene, parentLogical, generation);
		EntityAI holder = null;
		if (parentRecord && parentRecord.m_RefEnt)
			holder = EntityAI.Cast(parentRecord.m_RefEnt);
		if (!holder || !holder.GetInventory())
			return null;
		bool bornInInventory = false;
		if (parentRecord.m_Cat == "actor" && slot == "Gloves")
			bornInInventory = true;
		if (bornInInventory)
			return PersistCreateDirectInInventory(holder, kind, slot, stripNoPersist);
		return PersistCreateByMovingIn(holder, kind, slot, stripNoPersist);
	}

	protected void HandleApplyScene(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string sceneId = GetStrArg(args, "scene_id", "");
		string sceneOpId = GetStrArg(args, "scene_op_id", "");
		string expectEpoch = GetStrArg(args, "expect_epoch", "");
		string pathway = GetStrArg(args, "q9_pathway", "a");
		int genN = (int)GetNumArg(args, "gen_n", 1.0);
		if (expectEpoch != m_Probe.GetInst())
		{
			PersistReject(res, "rejected", "stale_epoch");
			return;
		}
		bool pathwayKnown = false;
		if (pathway == "a")
			pathwayKnown = true;
		if (pathway == "b")
			pathwayKnown = true;
		if (!pathwayKnown)
		{
			PersistReject(res, "rejected", "bad_args");
			return;
		}
		if (sceneId == "" || sceneOpId == "" || genN < 1)
		{
			PersistReject(res, "rejected", "bad_args");
			return;
		}
		int scIdx = FindSceneIndex(sceneId);
		if (scIdx >= 0 && m_SceneLastOp.Get(scIdx) == sceneOpId)
		{
			res.status = "done";
			m_LastApplyRetainedSkipped = m_SceneLastRetainedSkipped.Get(scIdx);
			EmitApplyResponse(res.read, sceneId, sceneOpId, pathway, m_SceneGen.Get(scIdx), 1);
			return;
		}
		int rows = 0;
		if (args && args.rows > 0)
			rows = args.rows;
		if (rows < 1 || rows > 12)
		{
			PersistReject(res, "rejected", "bad_args");
			return;
		}
		array<string> scolWanted = new array<string>();
		scolWanted.Insert("logical_id");
		scolWanted.Insert("parent_id");
		scolWanted.Insert("cat");
		scolWanted.Insert("class_name");
		scolWanted.Insert("slot_name");
		array<string> ncolWanted = new array<string>();
		ncolWanted.Insert("req_x_m");
		ncolWanted.Insert("req_z_m");
		ncolWanted.Insert("req_yaw_deg");
		ncolWanted.Insert("health_mark_ratio");
		ncolWanted.Insert("must_vanish_b");
		array<int> scolPos = new array<int>();
		array<int> ncolPos = new array<int>();
		int missingCols = 0;
		int colScan = 0;
		while (colScan < scolWanted.Count())
		{
			int foundS = FindColIdx(args.scol, scolWanted.Get(colScan));
			scolPos.Insert(foundS);
			if (foundS < 0)
				missingCols = missingCols + 1;
			colScan = colScan + 1;
		}
		colScan = 0;
		while (colScan < ncolWanted.Count())
		{
			int foundN = FindColIdx(args.ncol, ncolWanted.Get(colScan));
			ncolPos.Insert(foundN);
			if (foundN < 0)
				missingCols = missingCols + 1;
			colScan = colScan + 1;
		}
		if (missingCols > 0)
		{
			PersistReject(res, "rejected", "bad_args");
			return;
		}
		if (!ReapplyResetWithRetention(sceneId, expectEpoch))
		{
			PersistReject(res, "error", "lease_expired");
			return;
		}
		array<string> retainedLids = new array<string>();
		int keptScan = 0;
		while (keptScan < m_Records.Count())
		{
			DSBX_QA_PersistRecord keptRec = m_Records.Get(keptScan);
			if (keptRec && keptRec.m_SceneId == sceneId && keptRec.m_ServerEpoch == expectEpoch)
				retainedLids.Insert(keptRec.m_LogicalId);
			keptScan = keptScan + 1;
		}
		m_LastApplyRetainedSkipped = 0;
		UpsertSceneMeta(sceneId, genN, sceneOpId);
		bool omitNoPersist = false;
		if (m_Probe.GetOpFault() == "omit_nopersistency_flag")
			omitNoPersist = true;
		string directorUid = "";
		int presentB = 0;
		int dirAliveB = 0;
		int invReadableB = 0;
		int invCountN = 0;
		int playersN = 0;
		Man director = FindOnlyPlayer(directorUid, playersN, presentB, dirAliveB, invReadableB, invCountN);
		int scolCount = args.scol.Count();
		int ncolCount = args.ncol.Count();
		int r = 0;
		while (r < rows)
		{
			if (!m_Probe.LeaseOk())
			{
				PersistReject(res, "error", "lease_expired");
				return;
			}
			int sBase = r * scolCount;
			int nBase = r * ncolCount;
			string logicalId = args.scell.Get(sBase + scolPos.Get(0));
			bool isRetainedRow = false;
			int rl = 0;
			while (rl < retainedLids.Count())
			{
				if (retainedLids.Get(rl) == logicalId)
					isRetainedRow = true;
				rl = rl + 1;
			}
			if (isRetainedRow)
			{
				m_LastApplyRetainedSkipped = m_LastApplyRetainedSkipped + 1;
				r = r + 1;
				continue;
			}
			string parentId = args.scell.Get(sBase + scolPos.Get(1));
			string cat = args.scell.Get(sBase + scolPos.Get(2));
			string className = args.scell.Get(sBase + scolPos.Get(3));
			string slotName = args.scell.Get(sBase + scolPos.Get(4));
			float reqX = args.ncell.Get(nBase + ncolPos.Get(0));
			float reqZ = args.ncell.Get(nBase + ncolPos.Get(1));
			float reqYaw = args.ncell.Get(nBase + ncolPos.Get(2));
			float hRatio = args.ncell.Get(nBase + ncolPos.Get(3));
			int mustVanishB = (int)args.ncell.Get(nBase + ncolPos.Get(4));
			float reqY = g_Game.SurfaceY(reqX, reqZ);
			vector targetPos = Vector(reqX, reqY, reqZ);
			Object createdObj = null;
			if (parentId == "")
				createdObj = PersistSpawnRootAt(className, targetPos, reqYaw, cat, pathway, omitNoPersist);
			if (parentId != "")
				createdObj = PersistSpawnSceneChild(sceneId, parentId, genN, className, slotName, omitNoPersist);
			DSBX_QA_PersistRecord rec = new DSBX_QA_PersistRecord();
			rec.m_ServerEpoch = m_Probe.GetInst();
			rec.m_SceneId = sceneId;
			rec.m_GenN = genN;
			rec.m_LogicalId = logicalId;
			rec.m_ParentId = parentId;
			rec.m_Cat = cat;
			rec.m_ClassName = className;
			rec.m_SlotName = slotName;
			rec.m_ReqXM = reqX;
			rec.m_ReqYM = reqY;
			rec.m_ReqZM = reqZ;
			rec.m_ReqYawDeg = reqYaw;
			rec.m_HealthMarkRatio = hRatio;
			rec.m_MustVanishB = mustVanishB;
			if (parentId != "" && slotName == "Gloves")
			{
				DSBX_QA_PersistRecord bornParent = FindRecordApplyParent(sceneId, parentId, genN);
				if (bornParent && bornParent.m_Cat == "actor")
					rec.m_BornInInventory = 1;
			}
			rec.m_SpawnTickMs = m_Probe.NowMs();
			rec.m_RefEnt = createdObj;
			if (createdObj)
			{
				rec.m_OkB = 1;
				EntityAI ent = EntityAI.Cast(createdObj);
				float maxHp = -1.0;
				float healthNow = -1.0;
				if (ent) rec.m_HealthMarkB = ApplyQaHealthMark(ent,  hRatio, maxHp, healthNow);
				if (ent) rec.m_MaxHp = maxHp;
				if (ent) rec.m_HealthHp = healthNow;
				if (!ent && hRatio > 0.0) rec.m_HealthMarkB = 0;
				if (createdObj.IsAlive())
					rec.m_AliveB = 1;
				vector q9Pos = createdObj.GetPosition();
				vector q9Ori = createdObj.GetOrientation();
				rec.m_Q9XM = q9Pos[0];
				rec.m_Q9YM = q9Pos[1];
				rec.m_Q9ZM = q9Pos[2];
				rec.m_Q9DxM = q9Pos[0] - targetPos[0];
				rec.m_Q9DyM = q9Pos[1] - targetPos[1];
				rec.m_Q9DzM = q9Pos[2] - targetPos[2];
				rec.m_Q9Err3dM = vector.Distance(q9Pos, targetPos);
				rec.m_Q9YawDeg = q9Ori[0];
				rec.m_Q9PitchDeg = q9Ori[1];
				rec.m_Q9RollDeg = q9Ori[2];
				bool creatureCat = false;
				if (cat == "infected")
					creatureCat = true;
				if (cat == "animal")
					creatureCat = true;
				DayZCreatureAI creature = DayZCreatureAI.Cast(createdObj);
				if (creatureCat && pathway == "b" && creature)
					creature.InitAIAgent(g_Game.GetWorld().GetAIWorld().CreateDefaultGroup());
				if (creatureCat && creature && creature.GetAIAgent() != null)
					rec.m_AiAgentB = 1;
				rec.m_NetId = FormatNetId(createdObj);
				rec.m_PersId = FormatPersId(createdObj);
				string locKind = "";
				string parentClass = "";
				string parentNetId = "";
				string obsSlot = "";
				string ownerUid = "";
				int invCh = 0;
				ReadRealLocation(createdObj, director, directorUid, locKind, parentClass, parentNetId, obsSlot, ownerUid, invCh);
				rec.m_ObsLocKind = locKind;
				rec.m_ObsParentNetId = parentNetId;
				rec.m_ObsSlotName = obsSlot;
			}
			if (!createdObj) { rec.m_MaxHp = 0.0; rec.m_HealthHp = 0.0; rec.m_HealthMarkB = 0; rec.m_AliveB = 0; rec.m_AiAgentB = 0; }
			m_Records.Insert(rec);
			r = r + 1;
		}
		int scIdxDone = FindSceneIndex(sceneId);
		if (scIdxDone >= 0)
			m_SceneLastRetainedSkipped.Set(scIdxDone, m_LastApplyRetainedSkipped);
		res.status = "done";
		EmitApplyResponse(res.read, sceneId, sceneOpId, pathway, genN, 0);
	}

	protected void HandleResetScene(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string sceneId = GetStrArg(args, "scene_id", "");
		string resetOpId = GetStrArg(args, "reset_op_id", "");
		string expectEpoch = GetStrArg(args, "expect_epoch", "");

		if (expectEpoch == "" || expectEpoch != m_Probe.GetInst())
		{
			res.status = "rejected";
			res.reason = "stale_epoch";
			return;
		}
		if (sceneId == "" || resetOpId == "")
		{
			res.status = "rejected";
			res.reason = "bad_args";
			return;
		}

		int scIdx = FindSceneIndex(sceneId);
		int targetGenN = 1;
		if (scIdx >= 0)
			targetGenN = m_SceneGen.Get(scIdx);

		string opFault = m_Probe.GetOpFault();
		bool wipeRadiusFault = (opFault == "reset_wipe_radius_25m");

		float refX = 0.0;
		float refZ = 0.0;
		bool hasRefPos = false;

		for (int i = 0; i < m_Records.Count(); i++)
		{
			DSBX_QA_PersistRecord rec = m_Records.Get(i);
			if (!rec || rec.m_SceneId != sceneId || rec.m_GenN != targetGenN)
				continue;
			rec.m_RetainOnReset = false;
			rec.m_ForeignDescendantsN = 0;
			if (!hasRefPos && rec.m_ParentId == "")
			{
				refX = rec.m_ReqXM;
				refZ = rec.m_ReqZM;
				hasRefPos = true;
			}
		}

		if (!wipeRadiusFault)
		{
			for (int j = 0; j < m_Records.Count(); j++)
			{
				DSBX_QA_PersistRecord cand = m_Records.Get(j);
				if (!cand || cand.m_SceneId != sceneId || cand.m_GenN != targetGenN || !cand.m_RefEnt)
					continue;
				int fCnt = CountForeignDescendants(cand.m_RefEnt, expectEpoch, sceneId, targetGenN);
				if (fCnt > 0)
				{
					cand.m_RetainOnReset = true;
					cand.m_ForeignDescendantsN = fCnt;
					EntityAI curEnt = EntityAI.Cast(cand.m_RefEnt);
					while (curEnt)
					{
						EntityAI anc = curEnt.GetHierarchyParent();
						if (!anc)
							break;
						DSBX_QA_PersistRecord ancRec = FindRecordByObject(anc);
						if (ancRec && ancRec.m_SceneId == sceneId && ancRec.m_GenN == targetGenN)
						{
							ancRec.m_RetainOnReset = true;
							if (ancRec.m_ForeignDescendantsN < fCnt)
								ancRec.m_ForeignDescendantsN = fCnt;
						}
						curEnt = anc;
					}
				}
			}
		}

		int deletedN = 0;
		for (int p1 = m_Records.Count() - 1; p1 >= 0; p1--)
		{
			if (!m_Probe.LeaseOk())
			{
				res.status = "error";
				res.reason = "lease_expired";
				return;
			}
			DSBX_QA_PersistRecord childRec = m_Records.Get(p1);
			if (!childRec || childRec.m_SceneId != sceneId || childRec.m_GenN != targetGenN)
				continue;
			if (childRec.m_ParentId == "" || childRec.m_RetainOnReset)
				continue;
			if (IsObjectAlive(childRec.m_RefEnt))
			{
				g_Game.ObjectDelete(childRec.m_RefEnt);
				deletedN = deletedN + 1;
			}
			childRec.m_RefEnt = null;
			m_Records.RemoveOrdered(p1);
		}

		for (int p2 = m_Records.Count() - 1; p2 >= 0; p2--)
		{
			if (!m_Probe.LeaseOk())
			{
				res.status = "error";
				res.reason = "lease_expired";
				return;
			}
			DSBX_QA_PersistRecord rootRec = m_Records.Get(p2);
			if (!rootRec || rootRec.m_SceneId != sceneId || rootRec.m_GenN != targetGenN)
				continue;
			if (rootRec.m_ParentId != "" || rootRec.m_RetainOnReset)
				continue;
			if (IsObjectAlive(rootRec.m_RefEnt))
			{
				g_Game.ObjectDelete(rootRec.m_RefEnt);
				deletedN = deletedN + 1;
			}
			rootRec.m_RefEnt = null;
			m_Records.RemoveOrdered(p2);
		}

		if (wipeRadiusFault && hasRefPos)
		{
			vector wipeCenter = Vector(refX, g_Game.SurfaceY(refX, refZ), refZ);
			array<Object> nearObjs = new array<Object>();
			array<CargoBase> nearCargos = new array<CargoBase>();
			g_Game.GetObjectsAtPosition3D(wipeCenter, 25.0, nearObjs, nearCargos);
			for (int w = 0; w < nearObjs.Count(); w++)
			{
				Object wObj = nearObjs.Get(w);
				if (!IsObjectAlive(wObj))
					continue;
				EntityAI wEnt = EntityAI.Cast(wObj);
				if (!wEnt || wEnt.IsMan())
					continue;
				if (!m_Probe.LeaseOk())
				{
					res.status = "error";
					res.reason = "lease_expired";
					return;
				}
				g_Game.ObjectDelete(wObj);
			}
			for (int wr = m_Records.Count() - 1; wr >= 0; wr--)
			{
				DSBX_QA_PersistRecord remR = m_Records.Get(wr);
				if (remR && !IsObjectAlive(remR.m_RefEnt))
				{
					m_Records.RemoveOrdered(wr);
				}
			}
		}

		res.status = "done";
		EnsurePayloadHas(res.read);
		res.read.scol.Insert("logical_id");
		res.read.scol.Insert("class_name");
		res.read.scol.Insert("net_id");
		res.read.ncol.Insert("foreign_descendants_n");

		int retainedN = 0;
		for (int k = 0; k < m_Records.Count(); k++)
		{
			DSBX_QA_PersistRecord kept = m_Records.Get(k);
			if (!kept || kept.m_SceneId != sceneId || kept.m_GenN != targetGenN)
				continue;
			retainedN = retainedN + 1;
			res.read.scell.Insert(kept.m_LogicalId);
			res.read.scell.Insert(kept.m_ClassName);
			res.read.scell.Insert(kept.m_NetId);
			res.read.ncell.Insert(kept.m_ForeignDescendantsN);
		}
		res.read.rows = retainedN;

		string resetStatus = "ok";
		string resetReason = "clean";
		if (retainedN > 0)
		{
			resetStatus = "partial";
			resetReason = "foreign_content_retained";
		}

		PutStr(res.read, "reset_status", resetStatus);
		PutStr(res.read, "reason", resetReason);
		PutStr(res.read, "server_epoch", m_Probe.GetInst());
		PutStr(res.read, "scene_id", sceneId);
		PutStr(res.read, "reset_op_id", resetOpId);

		PutNum(res.read, "deleted_n", deletedN);
		PutNum(res.read, "retained_n", retainedN);
		PutNum(res.read, "tick_ms", m_Probe.NowMs());
		PutNum(res.read, "frame", m_Probe.m_Frame);
	}

	protected void HandleChildTransition(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string sceneId = GetStrArg(args, "scene_id", "");
		string logicalId = GetStrArg(args, "logical_id", "");
		string action = GetStrArg(args, "action", "");
		string expectEpoch = GetStrArg(args, "expect_epoch", "");
		string targetSceneId = GetStrArg(args, "target_scene_id", "");
		string targetParentId = GetStrArg(args, "target_parent_id", "");

		if (expectEpoch == "" || expectEpoch != m_Probe.GetInst())
		{
			res.status = "rejected";
			res.reason = "stale_epoch";
			return;
		}

		DSBX_QA_PersistRecord rec = FindRecord(sceneId, logicalId);
		if (!rec || !IsObjectAlive(rec.m_RefEnt))
		{
			res.status = "rejected";
			res.reason = "unknown_entity";
			return;
		}

		string wantedDirectorUid = GetStrArg(args, "director_uid", "");
		string directorUid = "";
		int presentB = 0;
		int aliveB = 0;
		int invReadableB = 0;
		int invCountN = 0;
		int playersN = 0;
		Man director = null;
		if (wantedDirectorUid != "")
			director = FindPlayerByUid(wantedDirectorUid, directorUid, presentB, aliveB, invReadableB, invCountN);
		else
			director = FindOnlyPlayer(directorUid, playersN, presentB, aliveB, invReadableB, invCountN);
		if (action == "move_to_director")
		{
			if (wantedDirectorUid == "")
			{
				res.status = "rejected";
				res.reason = "bad_args";
				return;
			}
			if (!director || presentB != 1 || aliveB != 1 || invReadableB != 1)
			{
				res.status = "rejected";
				res.reason = "director_not_ready";
				return;
			}
			if (!SubtreeBornInInventory(rec.m_RefEnt))
			{
				res.status = "rejected";
				res.reason = "bad_args";
				return;
			}
		}

		string preLocKind = "";
		string preParentClass = "";
		string preParentNetId = "";
		string preSlotName = "";
		string preOwnerUid = "";
		int preChildrenN = 0;
		ReadRealLocation(rec.m_RefEnt, director, directorUid, preLocKind, preParentClass, preParentNetId, preSlotName, preOwnerUid, preChildrenN);

		EntityAI itemEnt = EntityAI.Cast(rec.m_RefEnt);
		if (!itemEnt)
		{
			res.status = "error";
			res.reason = "transition_failed";
			return;
		}

		// E1: guarda antes del efecto de movimiento (LeaseOk, DSBX_QA_Probe.c:447).
		if (!m_Probe.LeaseOk())
		{
			res.status = "error";
			res.reason = "lease_expired";
			return;
		}

		// LocationSyncMoveEntity directo: la juncture de PlayerBase en SERVER no mueve en servidor (inventory.c:567,1057-1066; dayzplayerinventory.c:3728-3807).
		bool moveOk = false;
		if (action == "drop_to_ground")
		{
			EntityAI curOwner = itemEnt.GetHierarchyParent();
			InventoryLocation dropSrc = new InventoryLocation();
			InventoryLocation dropDst = new InventoryLocation();
			bool dropSrcOk = false;
			bool dropDstOk = false;
			if (itemEnt.GetInventory()) dropSrcOk = itemEnt.GetInventory().GetCurrentInventoryLocation(dropSrc);
			if (curOwner && dropSrcOk) dropDstOk = GameInventory.SetGroundPosByOwner(curOwner, itemEnt, dropDst);
			if (dropDstOk) moveOk = GameInventory.LocationSyncMoveEntity(dropSrc, dropDst);
		}
		else if (action == "move_to_director")
		{
			EntityAI dirEnt = EntityAI.Cast(director);
			InventoryLocation dirSrc = new InventoryLocation();
			InventoryLocation dirDst = new InventoryLocation();
			bool dirSrcOk = false;
			bool dirDstOk = false;
			if (itemEnt.GetInventory()) dirSrcOk = itemEnt.GetInventory().GetCurrentInventoryLocation(dirSrc);
			if (dirEnt && dirEnt.GetInventory() && dirSrcOk) dirDstOk = dirEnt.GetInventory().FindFreeLocationFor(itemEnt, FindInventoryLocationType.ANY, dirDst);
			if (dirDstOk) moveOk = GameInventory.LocationSyncMoveEntity(dirSrc, dirDst);
		}
		else if (action == "move_to_container")
		{
			DSBX_QA_PersistRecord targetRec = FindRecord(targetSceneId, targetParentId);
			if (!targetRec || !IsObjectAlive(targetRec.m_RefEnt))
			{
				res.status = "rejected";
				res.reason = "unknown_entity";
				return;
			}
			EntityAI targetEnt = EntityAI.Cast(targetRec.m_RefEnt);
			if (targetEnt && targetEnt.GetHierarchyRootPlayer() != null && !SubtreeBornInInventory(rec.m_RefEnt))
			{
				res.status = "rejected";
				res.reason = "bad_args";
				return;
			}
			if (targetEnt && targetEnt.GetInventory())
			{
				moveOk = targetEnt.GetInventory().TakeEntityToTargetCargo(InventoryMode.SERVER, targetEnt, itemEnt);
			}
		}
		else
		{
			res.status = "rejected";
			res.reason = "bad_args";
			return;
		}

		if (!moveOk)
		{
			res.status = "error";
			res.reason = "transition_failed";
			return;
		}

		string postLocKind = "";
		string postParentClass = "";
		string postParentNetId = "";
		string postSlotName = "";
		string postOwnerUid = "";
		int postChildrenN = 0;
		ReadRealLocation(rec.m_RefEnt, director, directorUid, postLocKind, postParentClass, postParentNetId, postSlotName, postOwnerUid, postChildrenN);

		bool finalLocOk = false;
		if (action == "drop_to_ground" && postLocKind == "ground") finalLocOk = true;
		if (action == "move_to_director" && directorUid != "" && postOwnerUid == directorUid) finalLocOk = true;
		if (action == "move_to_container") finalLocOk = true;
		if (!finalLocOk)
		{
			res.status = "error";
			res.reason = "transition_failed";
			return;
		}

		rec.m_ObsLocKind = postLocKind;
		rec.m_ObsParentNetId = postParentNetId;
		rec.m_ObsSlotName = postSlotName;

		vector pos = rec.m_RefEnt.GetPosition();
		vector ori = rec.m_RefEnt.GetOrientation();

		res.status = "done";
		EnsurePayloadHas(res.read);
		PutStr(res.read, "transition_status", "ok");
		PutStr(res.read, "net_id", rec.m_NetId);
		PutStr(res.read, "pre_loc_kind", preLocKind);
		PutStr(res.read, "pre_parent_net_id", preParentNetId);
		PutStr(res.read, "pre_slot_name", preSlotName);
		PutStr(res.read, "pre_owner_uid", preOwnerUid);
		PutStr(res.read, "post_loc_kind", postLocKind);
		PutStr(res.read, "post_parent_net_id", postParentNetId);
		PutStr(res.read, "post_slot_name", postSlotName);
		PutStr(res.read, "post_owner_uid", postOwnerUid);

		PutNum(res.read, "pos_x_m", pos[0]);
		PutNum(res.read, "pos_y_m", pos[1]);
		PutNum(res.read, "pos_z_m", pos[2]);
		PutNum(res.read, "yaw_deg", ori[0]);
		PutNum(res.read, "pitch_deg", ori[1]);
		PutNum(res.read, "roll_deg", ori[2]);
		PutNum(res.read, "tick_ms", m_Probe.NowMs());
		PutNum(res.read, "frame", m_Probe.m_Frame);
	}

	protected Object PersistRawGround(string kind, vector where, float yaw, int flags)
	{
		Object made = g_Game.CreateObjectEx(kind, where, flags, FLAG_RF_DEFAULT);
		if (made)
			made.SetPosition(where);
		if (made)
			made.SetOrientation(Vector(yaw, 0.0, 0.0));
		return made;
	}

	protected Object PersistRawRecordContainer(DSBX_QA_PersistRecord parentRecord, string kind, DSBX_QA_Result res)
	{
		m_PersistRawKitOk = true;
		EntityAI holder = null;
		if (parentRecord && IsObjectAlive(parentRecord.m_RefEnt))
			holder = EntityAI.Cast(parentRecord.m_RefEnt);
		if (!holder || !holder.GetInventory())
			return null;
		InventoryLocation directSpot = new InventoryLocation();
		Object direct = null;
		if (holder.GetInventory().FindFirstFreeLocationForNewEntity(kind, FindInventoryLocationType.CARGO, directSpot))
			direct = GameInventory.LocationCreateEntity(directSpot, kind, FLAG_ECE_IN_INVENTORY, FLAG_RF_DEFAULT);
		if (direct)
			return direct;
		EntityAI kitHolder = holder.GetHierarchyParent();
		InventoryLocation kitHere = new InventoryLocation();
		InventoryLocation kitGround = new InventoryLocation();
		InventoryLocation kitInside = new InventoryLocation();
		InventoryLocation kitReturnFrom = new InventoryLocation();
		InventoryLocation kitReturnTo = new InventoryLocation();
		bool kitHereOk = holder.GetInventory().GetCurrentInventoryLocation(kitHere);
		bool kitGroundOk = false;
		bool kitOut = false;
		bool kitReturnFound = false;
		bool kitReturned = false;
		if (kitHolder && kitHereOk)
			kitGroundOk = GameInventory.SetGroundPosByOwner(kitHolder, holder, kitGround);
		if (kitGroundOk)
			kitOut = GameInventory.LocationSyncMoveEntity(kitHere, kitGround);
		Object nested = null;
		if (kitOut && holder.GetInventory().FindFirstFreeLocationForNewEntity(kind, FindInventoryLocationType.CARGO, kitInside))
			nested = GameInventory.LocationCreateEntity(kitInside, kind, FLAG_ECE_IN_INVENTORY, FLAG_RF_DEFAULT);
		bool returnFromOk = false;
		if (kitOut)
			returnFromOk = holder.GetInventory().GetCurrentInventoryLocation(kitReturnFrom);
		if (returnFromOk && kitHolder && kitHolder.GetInventory())
			kitReturnFound = kitHolder.GetInventory().FindFreeLocationFor(holder, FindInventoryLocationType.CARGO, kitReturnTo);
		if (kitReturnFound)
			kitReturned = GameInventory.LocationSyncMoveEntity(kitReturnFrom, kitReturnTo);
		m_PersistRawKitOk = false;
		if (kitOut && kitReturned && nested)
			m_PersistRawKitOk = true;
		return nested;
	}

	protected void HandleSpawnRaw(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string tag = GetStrArg(args, "tag", "");
		string mode = GetStrArg(args, "mode", "");
		string className = GetStrArg(args, "class_name", "");
		string childCargoClass = GetStrArg(args, "child_cargo_class", "");
		string targetSceneId = GetStrArg(args, "target_scene_id", "");
		string targetParentId = GetStrArg(args, "target_parent_id", "");
		string targetNetId;
		targetNetId = GetStrArg(args, "target_net_id", "");
		float xm = GetNumArg(args, "x_m", 0.0);
		float zm = GetNumArg(args, "z_m", 0.0);
		float yawDeg = GetNumArg(args, "yaw_deg", 0.0);
		float hRatio = GetNumArg(args, "health_mark_ratio", 1.0);
		if (!m_Probe.LeaseOk())
		{
			PersistReject(res, "error", "lease_expired");
			return;
		}
		m_PersistRawKitOk = true;
		float ym = g_Game.SurfaceY(xm, zm);
		vector targetPos = Vector(xm, ym, zm);
		Object createdObj = null;
		Object childObj = null;
		if (mode == "foreign_ground")
			createdObj = PersistRawGround(className, targetPos, yawDeg, FLAGS_STATIC);
		if (mode == "foreign_in_container" && targetNetId != "")
		{
			int tHigh = 0; int tLow = 0;
			bool netIdOk = ParseNetIdStr(targetNetId, tHigh, tLow);
			if (!netIdOk)
			{
				PersistReject(res, "rejected", "bad_args");
				return;
			}
			Object netObj = g_Game.GetObjectByNetworkId(tLow, tHigh);
			EntityAI netParEnt = EntityAI.Cast(netObj);
			bool netParBad = false;
			if (!netParEnt)
				netParBad = true;
			if (netParEnt && !IsObjectAlive(netParEnt))
				netParBad = true;
			if (netParBad)
			{
				PersistReject(res, "rejected", "target_not_found");
				return;
			}
			InventoryLocation netLoc;
			netLoc = new InventoryLocation();
			bool netLocFound = false;
			if (netParEnt.GetInventory())
				netLocFound = netParEnt.GetInventory().FindFirstFreeLocationForNewEntity(className, FindInventoryLocationType.CARGO, netLoc);
			if (!netLocFound)
			{
				PersistReject(res, "rejected", "no_cargo_space");
				return;
			}
			bool netLocWrong = false;
			if (netLoc.GetType() != InventoryLocationType.CARGO  ||  netLoc.GetParent() != netParEnt)
				netLocWrong = true;
			if (netLocWrong)
			{
				PersistReject(res, "rejected", "no_cargo_space");
				return;
			}
			if (!netLocWrong) createdObj = GameInventory.LocationCreateEntity(netLoc, className, FLAG_ECE_IN_INVENTORY, FLAG_RF_DEFAULT);
		}
		if (mode == "foreign_in_container" && targetNetId == "")
		{
			DSBX_QA_PersistRecord parRec = FindRecord(targetSceneId, targetParentId);
			createdObj = PersistRawRecordContainer(parRec, className, res);
		}
		if (mode == "persistent_control")
		{
			createdObj = PersistRawGround(className, targetPos, yawDeg, FLAG_ECE_PLACE_ON_SURFACE);
			if (createdObj && childCargoClass != "" && !m_Probe.LeaseOk())
			{
				PersistReject(res, "error", "lease_expired");
				return;
			}
			if (createdObj && childCargoClass != "")
			{
				EntityAI ctrlEnt = EntityAI.Cast(createdObj);
				Barrel_ColorBase barrelEnt = Barrel_ColorBase.Cast(createdObj);
				if (barrelEnt && !barrelEnt.IsOpen())
					barrelEnt.Open();
				if (ctrlEnt && ctrlEnt.GetInventory())
				{
					InventoryLocation chLoc = new InventoryLocation();
					if (ctrlEnt.GetInventory().FindFirstFreeLocationForNewEntity(childCargoClass, FindInventoryLocationType.CARGO, chLoc))
					{
						childObj = GameInventory.LocationCreateEntity(chLoc, childCargoClass, FLAG_ECE_IN_INVENTORY, FLAG_RF_DEFAULT);
						EntityAI childEnt = EntityAI.Cast(childObj);
						float chMaxHp = -1.0;
						float chHealthHp = -1.0;
						if (childEnt) ApplyQaHealthMark(childEnt,  hRatio, chMaxHp, chHealthHp);
					}
				}
			}
		}
		if (!createdObj)
		{
			PersistReject(res, "error", "spawn_failed");
			return;
		}
		float maxHp = 100.0;
		float healthHp = 100.0;
		int healthMarkB;
		healthMarkB = 1;
		EntityAI cEnt = EntityAI.Cast(createdObj);
		if (cEnt) healthMarkB = ApplyQaHealthMark(cEnt,  hRatio, maxHp, healthHp);
		if (!cEnt && hRatio > 0.0) healthMarkB = 0;
		string directorUid = "";
		int presentB = 0;
		int aliveB = 0;
		int invReadableB = 0;
		int invCountN = 0;
		int playersN = 0;
		Man director = FindOnlyPlayer(directorUid, playersN, presentB, aliveB, invReadableB, invCountN);
		string obsLocKind = "";
		string obsParentClass = "";
		string obsParentNetId = "";
		string obsSlotName = "";
		string obsOwnerUid = "";
		int invChildren = 0;
		ReadRealLocation(createdObj, director, directorUid, obsLocKind, obsParentClass, obsParentNetId, obsSlotName, obsOwnerUid, invChildren);
		if (mode == "persistent_control" && childCargoClass != "" && invChildren != 1)
		{
			PersistReject(res, "error", "child_spawn_failed");
			return;
		}
		bool foreignFailed = false;
		if (mode == "foreign_in_container" && !m_PersistRawKitOk)
			foreignFailed = true;
		if (mode == "foreign_in_container" && obsLocKind != "cargo")
			foreignFailed = true;
		if (foreignFailed)
		{
			PersistReject(res, "error", "spawn_failed");
			return;
		}
		string netId = FormatNetId(createdObj);
		string persId = FormatPersId(createdObj);
		vector pos = createdObj.GetPosition();
		vector ori = createdObj.GetOrientation();
		DSBX_QA_PersistRawRecord rawRec = new DSBX_QA_PersistRawRecord();
		rawRec.m_Tag = tag;
		rawRec.m_Mode = mode;
		rawRec.m_ClassName = className;
		rawRec.m_NetId = netId;
		rawRec.m_PersId = persId;
		rawRec.m_SpawnTickMs = m_Probe.NowMs();
		rawRec.m_MaxHp = maxHp;
		rawRec.m_HealthHp = healthHp;
		rawRec.m_HealthMarkB =  healthMarkB;
		rawRec.m_RefEnt = createdObj;
		rawRec.m_ChildEnt = childObj;
		m_RawRecords.Insert(rawRec);
		res.status = "done";
		EnsurePayloadHas(res.read);
		PutStr(res.read, "spawn_status", "ok");
		PutStr(res.read, "tag", tag);
		PutStr(res.read, "class_name", className);
		PutStr(res.read, "net_id", netId);
		PutStr(res.read, "pers_id", persId);
		PutStr(res.read, "obs_loc_kind", obsLocKind);
		PutStr(res.read, "obs_parent_net_id", obsParentNetId);
		PutStr(res.read, "obs_slot_name", obsSlotName);
		PutNum(res.read, "pos_x_m", pos[0]);
		PutNum(res.read, "pos_y_m", pos[1]);
		PutNum(res.read, "pos_z_m", pos[2]);
		PutNum(res.read, "yaw_deg", ori[0]);
		PutNum(res.read, "pitch_deg", ori[1]);
		PutNum(res.read, "roll_deg", ori[2]);
		PutNum(res.read, "max_hp", maxHp);
		PutNum(res.read, "health_hp", healthHp);
		PutNum(res.read, "child_count_n", invChildren);
		PutNum(res.read, "tick_ms", m_Probe.NowMs());
		PutNum(res.read, "frame", m_Probe.m_Frame);
		PutNum(res.read, "health_mark_b",  healthMarkB);
	}

	protected int PersistCensusBlock(string job)
	{
		if (m_CensusLeaseAgeStartMs > (float)m_Probe.GetLeaseMs())
		{
			m_CaptureFailed = true;
			m_CaptureFailReason = "lease_expired";
			m_CaptureFailJobId = job;
			return 1;
		}
		bool overTime = false;
		if (m_CensusCaptureStartMs > 0.0 && m_Probe.NowMs() - m_CensusCaptureStartMs > CENSUS_CAPTURE_BUDGET_MS)
			overTime = true;
		if (overTime)
		{
			m_CaptureFailed = true;
			m_CaptureFailReason = "capture_budget_exceeded";
			m_CaptureFailJobId = job;
			return 2;
		}
		return 0;
	}

	protected bool PersistCensusSeen(array<Object> bag, Object item)
	{
		int at = 0;
		while (at < bag.Count())
		{
			if (bag.Get(at) == item)
				return true;
			at = at + 1;
		}
		return false;
	}

	protected bool AppendEntityCensusRow(string jobId, Object obj, int inRadiusB, Man director, string directorUid, array<Object> seen, bool withSurface)
	{
		if (PersistCensusBlock(jobId) != 0)
			return false;
		if (!IsObjectAlive(obj))
			return true;
		if (PersistCensusSeen(seen, obj))
			return true;
		string locKind = "";
		string parentClass = "";
		string parentNetId = "";
		string slotName = "";
		string ownerUid = "";
		int invChildrenN = 0;
		ReadRealLocation(obj,  director, directorUid, locKind, parentClass, parentNetId, slotName, ownerUid, invChildrenN, withSurface, withSurface);
		int ownB = 0;
		string ownLogicalId = "";
		float spawnTickMs = 0.0;
		DSBX_QA_PersistRecord rec = FindRecordByObject(obj);
		if (rec)
		{
			ownB = 1;
			ownLogicalId = rec.m_LogicalId;
			spawnTickMs = rec.m_SpawnTickMs;
		}
		int aliveB = 0;
		if (obj.IsAlive())
			aliveB = 1;
		int aiAgentB = 0;
		DayZCreatureAI creature = DayZCreatureAI.Cast(obj);
		if (creature && creature.GetAIAgent() != null)
			aiAgentB = 1;
		vector pos = obj.GetPosition();
		vector ori = obj.GetOrientation();
		float maxHp = 0.0;
		float healthHp = 0.0;
		if (EntityAI.Cast(obj)) { if (IsQaCreated(obj)) ReadQaHealth(obj,  maxHp, healthHp); else ReadHealth(obj, maxHp, healthHp); }
		array<string> svals = new array<string>();
		svals.Insert(obj.GetType());
		svals.Insert(locKind);
		svals.Insert(parentClass);
		svals.Insert(parentNetId);
		svals.Insert(slotName);
		svals.Insert(ownerUid);
		svals.Insert(ownLogicalId);
		svals.Insert(FormatNetId(obj));
		svals.Insert(FormatPersId(obj));
		array<float> nvals = new array<float>();
		nvals.Insert(ownB);
		nvals.Insert(inRadiusB);
		nvals.Insert(aliveB);
		nvals.Insert(aiAgentB);
		nvals.Insert(pos[0]);
		nvals.Insert(pos[1]);
		nvals.Insert(pos[2]);
		nvals.Insert(ori[0]);
		nvals.Insert(ori[1]);
		nvals.Insert(ori[2]);
		nvals.Insert(maxHp);
		nvals.Insert(healthHp);
		nvals.Insert(invChildrenN);
		nvals.Insert(spawnTickMs);
		if (withSurface) { nvals.Insert(g_Game.SurfaceY(pos[0], pos[2])); }
		bool appended = m_Jobs.AppendRow(jobId, nvals, svals);
		if (!appended)
		{
			m_CaptureFailed = true;
			m_CaptureFailReason = "capture_truncated";
			m_CaptureFailJobId = jobId;
			return false;
		}
		seen.Insert(obj);
		return true;
	}

	protected void HandleCensusStart(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string areaTag = GetStrArg(args, "area_tag", "");
		float centerX = GetNumArg(args, "center_x_m", 0.0);
		float centerZ = GetNumArg(args, "center_z_m", 0.0);
		float radiusM = GetNumArg(args, "radius_m", 60.0);
		int includeDirectorB = (int)GetNumArg(args, "include_director_b", 0.0);
		float selectAllRaw = GetNumArg(args,  "select_all_entityai_b", 0.0);
		string wantedDirectorUid = GetStrArg(args, "director_uid", "");
		bool censusBadArgs = false;
		if (selectAllRaw != 0.0 && selectAllRaw != 1.0) censusBadArgs = true;
		int selectAllB = (int) selectAllRaw;
		if (selectAllB == 1 && ( radiusM <= 0.0 || radiusM > CENSUS_ALL_RADIUS_MAX ))
			censusBadArgs = true;
		if (includeDirectorB != 0 && wantedDirectorUid == "")
			censusBadArgs = true;
		if (censusBadArgs)
		{
			PersistReject(res, "rejected", "bad_args");
			return;
		}
		if (m_PurgeJobId != "" && m_Jobs.GetState(m_PurgeJobId) == "running")
		{
			PersistReject(res, "rejected", "purge_pending");
			return;
		}
		array<string> censusNcol;
		censusNcol = m_CensusNcol;
		if (selectAllB == 1) censusNcol = m_CensusNcolAll;
		int pendingAt = 0;
		while (pendingAt < m_PendingFinishIds.Count())
		{
			if (m_PendingFinishIds.Get(pendingAt) != op.op_id)
				m_PendingFinishSeen.Set(pendingAt, 1);
			pendingAt = pendingAt + 1;
		}
		string opFaultEarly = m_Probe.GetOpFault();
		ref array<ref DSBX_QA_Job> heldJobs = new array<ref DSBX_QA_Job>();
		if (opFaultEarly == "census_resource_bypass")
		{
			int heldAt = 0;
			while (heldAt < m_PendingFinishIds.Count())
			{
				DSBX_QA_Job heldJob = m_Jobs.GetJob(m_PendingFinishIds.Get(heldAt));
				if (heldJob)
				{
					heldJob.m_Released = true;
					heldJobs.Insert(heldJob);
				}
				heldAt = heldAt + 1;
			}
		}
		string startErr = m_Jobs.StartJob(this, op.op_id, "per_census", censusNcol, m_CensusScol, 5, 4096, 900000.0, "stop");
		int restoreAt = 0;
		while (restoreAt < heldJobs.Count())
		{
			DSBX_QA_Job heldBack = heldJobs.Get(restoreAt);
			if (heldBack)
				heldBack.m_Released = false;
			restoreAt = restoreAt + 1;
		}
		if (startErr != "")
		{
			PersistReject(res, "rejected", startErr);
			return;
		}
		DSBX_QA_Job job = m_Jobs.GetJob(op.op_id);
		if (job)
			job.m_ExtHandlesDeadman = true;
		if (m_Probe.GetOpFault() == "drop_ctrl_pre_restart")
		{
			int dropAt = m_RawRecords.Count() - 1;
			while (dropAt >= 0)
			{
				DSBX_QA_PersistRawRecord rawEntry = m_RawRecords.Get(dropAt);
				if (rawEntry && rawEntry.m_Mode == "persistent_control")
				{
					if (IsObjectAlive(rawEntry.m_ChildEnt))
						g_Game.ObjectDelete(rawEntry.m_ChildEnt);
					if (IsObjectAlive(rawEntry.m_RefEnt))
						g_Game.ObjectDelete(rawEntry.m_RefEnt);
					m_RawRecords.RemoveOrdered(dropAt);
				}
				dropAt = dropAt - 1;
			}
		}
		string directorUid = "";
		int presentB = 0;
		int aliveB = 0;
		int invReadableB = 0;
		int invCountN = 0;
		int playersN = 0;
		Man director = null;
		if (wantedDirectorUid != "")
			director = FindPlayerByUid(wantedDirectorUid, directorUid, presentB, aliveB, invReadableB, invCountN);
		else
			director = FindOnlyPlayer(directorUid, playersN, presentB, aliveB, invReadableB, invCountN);
		array<Object> seen = new array<Object>();
		m_CaptureFailed = false;
		m_CaptureFailReason = "";
		m_CaptureFailJobId = "";
		m_CensusCaptureStartMs = m_Probe.NowMs();
		m_CensusLeaseAgeStartMs = m_Probe.LeaseAgeMs();
		if (!m_Probe.LeaseOk())
		{
			m_CaptureFailed = true;
			m_CaptureFailReason = "lease_expired";
			m_CaptureFailJobId = op.op_id;
		}
		vector centerPos = Vector(centerX, g_Game.SurfaceY(centerX, centerZ), centerZ);
		array<Object> nearObjs = new array<Object>();
		array<CargoBase> nearCargos = new array<CargoBase>();
		g_Game.GetObjectsAtPosition3D(centerPos, radiusM, nearObjs, nearCargos);
		int nearAt = 0;
		while (nearAt < nearObjs.Count())
		{
			Object obj = nearObjs.Get(nearAt);
			nearAt = nearAt + 1;
			if (!IsObjectAlive(obj))
				continue;
			if (director && obj == director)
				continue;
			bool includeObj = false;
			if (selectAllB == 1 && EntityAI.Cast(obj) != null)
				includeObj = true;
			if (selectAllB != 1 && FindRecordByObject(obj) != null)
				includeObj = true;
			if (selectAllB != 1 && IsSentinelClass(obj.GetType()))
				includeObj = true;
			if (selectAllB != 1 && DayZCreatureAI.Cast(obj) != null)
				includeObj = true;
			if (selectAllB == 1 && m_Jobs.GetState(op.op_id) != "running")
				break;
			if (!includeObj)
				continue;
			if (!AppendEntityCensusRow(op.op_id, obj, 1, director, directorUid, seen, selectAllB == 1)) break;
			EntityAI ent = EntityAI.Cast(obj);
			if (ent && ent.GetInventory())
			{
				array<EntityAI> subItems = new array<EntityAI>();
				ent.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, subItems);
				bool subOk = true;
				int sub = 0;
				while (sub < subItems.Count())
				{
					EntityAI subEnt = subItems.Get(sub);
					sub = sub + 1;
					if (subEnt && subEnt != ent && !AppendEntityCensusRow(op.op_id, subEnt, 1, director, directorUid, seen, selectAllB == 1))
					{
						subOk = false;
						break;
					}
				}
				if (!subOk)
					break;
			}
		}
		int recLimit = 0;
		if (selectAllB != 1) recLimit = m_Records.Count();
		int recAt = 0;
		while (recAt < recLimit)
		{
			DSBX_QA_PersistRecord rec = m_Records.Get(recAt);
			recAt = recAt + 1;
			bool ownCreature = false;
			if (rec && IsObjectAlive(rec.m_RefEnt) && rec.m_Cat == "infected")
				ownCreature = true;
			if (rec && IsObjectAlive(rec.m_RefEnt) && rec.m_Cat == "animal")
				ownCreature = true;
			if (!ownCreature)
				continue;
			float dx = rec.m_ReqXM - centerX;
			float dz = rec.m_ReqZM - centerZ;
			if (dx * dx + dz * dz <= radiusM * radiusM && !AppendEntityCensusRow(op.op_id, rec.m_RefEnt, 0, director, directorUid, seen, selectAllB == 1))
				break;
		}
		if (includeDirectorB != 0 && director)
		{
			EntityAI dirEnt = EntityAI.Cast(director);
			if (dirEnt && dirEnt.GetInventory())
			{
				array<EntityAI> dirItems = new array<EntityAI>();
				dirEnt.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, dirItems);
				int di = 0;
				while (di < dirItems.Count())
				{
					EntityAI dItem = dirItems.Get(di);
					di = di + 1;
					if (dItem && dItem != dirEnt && !AppendEntityCensusRow(op.op_id, dItem, 1, director, directorUid, seen, selectAllB == 1))
						break;
				}
			}
		}
		m_PendingFinishIds.Insert(op.op_id);
		m_PendingFinishTicks.Insert(CENSUS_FINISH_AFTER_ATTEMPT_TICKS);
		m_PendingFinishSeen.Insert(0);
		m_PendingFinishAgeMs.Insert(0.0);
		res.status = "done";
		m_Jobs.FillStartRead(res.read, op.op_id, "per_census");
		PutStr(res.read, "area_tag", areaTag);
		PutStr(res.read, "server_epoch", m_Probe.GetInst());
		PutStr(res.read, "director_uid", directorUid);
		float captureEndMs = m_Probe.NowMs();
		PutNum(res.read, "snap_tick_ms", m_CensusCaptureStartMs);
		PutNum(res.read, "capture_wall_ms", captureEndMs - m_CensusCaptureStartMs);
		PutNum(res.read, "snap_frame", m_Probe.m_Frame);
		PutNum(res.read, "rows_captured_n", seen.Count());
		PutNum(res.read, "center_x_m", centerX);
		PutNum(res.read, "center_z_m", centerZ);
		PutNum(res.read, "radius_m", radiusM);
		PutNum(res.read, "director_present_b", presentB);
		PutNum(res.read, "director_alive_b", aliveB);
		PutNum(res.read, "director_inv_readable_b", invReadableB);
		PutNum(res.read, "director_inv_count_n", invCountN);
	}

	protected void ResetWitness()
	{
		DSBX_QA_Witness.Disable();
		m_WitnessJobId = "";
		m_WitnessEndMs = 0.0;
		m_WitnessK = 0;
		m_WitnessWindowClosed = false;
		m_WitnessFollow.Clear();
	}

	protected void HandleWitnessStart(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string witnessTag = GetStrArg(args, "witness_tag", "");
		if (!HasNumArg(args, "center_x_m") || !HasNumArg(args, "center_z_m") || !HasNumArg(args, "radius_m") || !HasNumArg(args, "window_ms"))
		{
			res.status = "rejected";
			res.reason = "bad_args";
			return;
		}
		float centerX = GetNumArg(args, "center_x_m", 0.0);
		float centerZ = GetNumArg(args, "center_z_m", 0.0);
		float radiusM = GetNumArg(args, "radius_m", 0.0);
		float windowMs = GetNumArg(args, "window_ms", 0.0);
		float kRaw = GetNumArg(args, "witness_follow_ticks", WITNESS_K_DEFAULT);
		int followK = (int)kRaw;
		// Los rechazos salen antes de StartJob y de encender el gancho: sin efectos.
		if (radiusM <= 0.0 || radiusM > WITNESS_RADIUS_MAX || windowMs <= 0.0 || windowMs > WITNESS_WINDOW_MAX_MS)
		{
			res.status = "rejected";
			res.reason = "bad_args";
			return;
		}
		float kBack = followK;
		if (kRaw != kBack || followK < 1 || followK > WITNESS_K_MAX)
		{
			res.status = "rejected";
			res.reason = "bad_args";
			return;
		}

		string err = m_Jobs.StartJob(this, op.op_id, "per_witness", m_WitnessNcol, m_WitnessScol, 5, 4096, windowMs + WITNESS_TAIL_MS, "stop");
		if (err != "")
		{
			res.status = "rejected";
			res.reason = err;
			return;
		}

		float startMs = m_Probe.NowMs();
		m_WitnessJobId = op.op_id;
		m_WitnessEndMs = startMs + windowMs;
		m_WitnessK = followK;
		m_WitnessWindowClosed = false;
		m_WitnessFollow.Clear();
		DSBX_QA_Witness.Enable(centerX, centerZ, radiusM, m_WitnessEndMs, m_Probe.m_Frame);

		res.status = "done";
		m_Jobs.FillStartRead(res.read, op.op_id, "per_witness");
		PutStr(res.read, "witness_tag", witnessTag);
		PutStr(res.read, "server_epoch", m_Probe.GetInst());

		PutNum(res.read, "start_tick_ms", startMs);
		PutNum(res.read, "start_frame", m_Probe.m_Frame);
		PutNum(res.read, "center_x_m", centerX);
		PutNum(res.read, "center_z_m", centerZ);
		PutNum(res.read, "radius_m", radiusM);
		PutNum(res.read, "window_ms", windowMs);
		PutNum(res.read, "witness_follow_ticks", followK);
	}

	// Una fila del testigo. false si el JobMgr la rechazo (tope de filas: el trabajo ya esta en failed).
	protected bool AppendWitnessRow(string jobId, int sampleIdx, string className, string netId, string parentNetId, float x, float y, float z, float yawDeg, float tickMs, int frame, int aiAgentB, int aliveB)
	{
		array<string> svals = new array<string>();
		svals.Insert(className);
		svals.Insert(netId);
		svals.Insert(parentNetId);

		array<float> nvals = new array<float>();
		nvals.Insert(sampleIdx);
		nvals.Insert(x);
		nvals.Insert(y);
		nvals.Insert(z);
		nvals.Insert(yawDeg);
		nvals.Insert(tickMs);
		nvals.Insert(frame);
		nvals.Insert(aiAgentB);
		nvals.Insert(aliveB);
		// surface_y_m, la ultima columna: SurfaceY(x, z) (game.c:1176; la misma API que el censo, :1705) con la x y la z
		// de ESTA fila, calculada al emitirla (muestra 0: la x y la z de EEInit, en el primer tick; no se consulta el motor
		// en EEInit). Si la entidad ya no existe, la fila lleva su ultima posicion conocida (la de EEInit si no hubo otra)
		// y surface_y_m se calcula con esa posicion.
		nvals.Insert(g_Game.SurfaceY(x, z));
		return m_Jobs.AppendRow(jobId, nvals, svals);
	}

	protected void TickWitness()
	{
		if (m_WitnessJobId == "")
			return;
		string jid = m_WitnessJobId;
		float now = m_Probe.NowMs();
		int frame = m_Probe.m_Frame;
		// Frame que se apunta en las capturas de EEInit del proximo intervalo.
		DSBX_QA_Witness.s_Frame = frame;

		// 1) Capturas de EEInit acumuladas desde el tick anterior. Se incorporan ANTES del seguimiento: su sample_idx 1 sale
		//    en este mismo tick, el frame siguiente al de EEInit (frames consecutivos 0, 1, ..., K). La fila sample_idx 0 se
		//    emite en este primer tick con la posicion, la orientacion, el tick_ms y el frame de EEInit, pero con el net_id y
		//    el parent_net_id leidos AHORA: en EEInit el motor aun no ha asignado el net_id (sale 0:0).
		int capN = DSBX_QA_Witness.s_Buf.Count();
		for (int c = 0; c < capN; c++)
		{
			DSBX_QA_WitnessCapture cap = DSBX_QA_Witness.s_Buf.Get(c);
			if (!cap)
				continue;
			DSBX_QA_PersistWitnessFollow nf = new DSBX_QA_PersistWitnessFollow();
			nf.m_Ent = cap.m_Ent;
			nf.m_ClassName = cap.m_ClassName;
			nf.m_NetId = cap.m_NetId;
			nf.m_ParentNetId = cap.m_ParentNetId;
			nf.m_LastX = cap.m_PosX;
			nf.m_LastY = cap.m_PosY;
			nf.m_LastZ = cap.m_PosZ;
			nf.m_LastYawDeg = cap.m_YawDeg;
			nf.m_EEInitTickMs = cap.m_TickMs;
			nf.m_EEInitFrame = cap.m_Frame;
			nf.m_AiAgentB = cap.m_AiAgentB;
			nf.m_PendingSample0 = true;
			nf.m_NextSample = 1;
			m_WitnessFollow.Insert(nf);
		}
		DSBX_QA_Witness.s_Buf.Clear();

		// 1b) Filas sample_idx 0 (antes que ninguna muestra de seguimiento: el orden de las filas no cambia).
		int s0Count = m_WitnessFollow.Count();
		for (int z = 0; z < s0Count; z++)
		{
			DSBX_QA_PersistWitnessFollow s0 = m_WitnessFollow.Get(z);
			if (!s0 || !s0.m_PendingSample0)
				continue;
			string s0Net = "0:0";
			string s0Parent = "";
			int s0Alive = 0;
			if (IsObjectAlive(s0.m_Ent))
			{
				s0Alive = 1;
				s0Net = FormatNetId(s0.m_Ent);
				EntityAI s0Ent = EntityAI.Cast(s0.m_Ent);
				if (s0Ent && s0Ent.GetHierarchyParent())
					s0Parent = FormatNetId(s0Ent.GetHierarchyParent());
			}
			s0.m_NetId = s0Net;
			s0.m_ParentNetId = s0Parent;
			s0.m_PendingSample0 = false;
			if (!AppendWitnessRow(jid, 0, s0.m_ClassName, s0Net, s0Parent, s0.m_LastX, s0.m_LastY, s0.m_LastZ, s0.m_LastYawDeg, s0.m_EEInitTickMs, s0.m_EEInitFrame, s0.m_AiAgentB, s0Alive))
				return;
		}

		// 2) Muestras de seguimiento (sample_idx 1..K), incluidas las recien capturadas.
		//    Si un AppendRow falla, el trabajo ya acabo (failed/rows_cap) y OnJobEnd limpio el estado: salir sin tocar nada.
		array<ref DSBX_QA_PersistWitnessFollow> keep = new array<ref DSBX_QA_PersistWitnessFollow>();
		int fCount = m_WitnessFollow.Count();
		for (int f = 0; f < fCount; f++)
		{
			DSBX_QA_PersistWitnessFollow fol = m_WitnessFollow.Get(f);
			if (!fol)
				continue;
			int aliveB = 0;
			int aiB = 0;
			string parentNetId = fol.m_ParentNetId;
			string netId = fol.m_NetId;
			if (IsObjectAlive(fol.m_Ent))
			{
				aliveB = 1;
				vector fpos = fol.m_Ent.GetPosition();
				vector fori = fol.m_Ent.GetOrientation();
				fol.m_LastX = fpos[0];
				fol.m_LastY = fpos[1];
				fol.m_LastZ = fpos[2];
				fol.m_LastYawDeg = fori[0];
				netId = FormatNetId(fol.m_Ent);
				EntityAI fEnt = EntityAI.Cast(fol.m_Ent);
				parentNetId = "";
				if (fEnt && fEnt.GetHierarchyParent())
					parentNetId = FormatNetId(fEnt.GetHierarchyParent());
				DayZCreatureAI fCreature = DayZCreatureAI.Cast(fol.m_Ent);
				if (fCreature && fCreature.GetAIAgent() != null)
					aiB = 1;
			}
			if (!AppendWitnessRow(jid, fol.m_NextSample, fol.m_ClassName, netId, parentNetId, fol.m_LastX, fol.m_LastY, fol.m_LastZ, fol.m_LastYawDeg, now, frame, aiB, aliveB))
				return;
			fol.m_NextSample = fol.m_NextSample + 1;
			if (fol.m_NextSample <= m_WitnessK)
				keep.Insert(fol);
		}
		m_WitnessFollow = keep;

		// 3) Vencida la ventana se deja de capturar; el trabajo acaba cuando ya no queda seguimiento pendiente.
		if (!m_WitnessWindowClosed && now >= m_WitnessEndMs)
		{
			m_WitnessWindowClosed = true;
			DSBX_QA_Witness.Disable();
		}
		if (m_WitnessWindowClosed && m_WitnessFollow.Count() == 0)
		{
			m_Jobs.EndJob(jid, "done", "");
		}
	}

	override void OnTick(float timeslice)
	{
		TickWitness();
		TickPurge();
		// BLOQ 6: la ocupacion se mantiene hasta acreditar el intento de B
		// (m_PendingFinishSeen) o hasta CENSUS_HOLD_MAX_MS desde el inicio;
		// el solapamiento se acredita con snap_tick de B < released_tick de A.
		int i = m_PendingFinishIds.Count() - 1;
		while (i >= 0)
		{
			string jid = m_PendingFinishIds.Get(i);
			float ageMs = m_PendingFinishAgeMs.Get(i) + timeslice * 1000.0;
			m_PendingFinishAgeMs.Set(i, ageMs);
			bool seenAttempt = m_PendingFinishSeen.Get(i) != 0;
			if (!seenAttempt && ageMs < CENSUS_HOLD_MAX_MS)
			{
				i = i - 1;
				continue;
			}
			int left = m_PendingFinishTicks.Get(i);
			if (left > 0)
			{
				m_PendingFinishTicks.Set(i, left - 1);
				i = i - 1;
				continue;
			}
			m_PendingFinishIds.RemoveOrdered(i);
			m_PendingFinishTicks.RemoveOrdered(i);
			m_PendingFinishSeen.RemoveOrdered(i);
			m_PendingFinishAgeMs.RemoveOrdered(i);
			if (m_CaptureFailed && m_CaptureFailJobId == jid)
			{
				// MEN 9: captura truncada -> trabajo fallido, nunca done.
				m_Jobs.EndJob(jid, "failed", m_CaptureFailReason);
			}
			else if (m_Jobs.IsDeadmanTripped(jid))
			{
				m_Jobs.EndJob(jid, "failed", "lease_expired");
			}
			else
			{
				m_Jobs.EndJob(jid, "done", "");
			}
			i = i - 1;
		}
	}

	override void OnJobEnd(string job_id, string state, string reason)
	{
		// Cualquier final del trabajo (done, rows_cap, lease_expired, job_timeout, shutdown) apaga el gancho.
		if (m_WitnessJobId == job_id)
		{
			ResetWitness();
		}
		if (m_PurgeJobId == job_id)
		{
			m_PurgeJobId = "";
			m_PurgeConfirmPersId = "";
			m_PurgeConfirmClass = "";
			m_PurgeConfirmNetId = "";
			m_PurgeConfirmParentPersId = "";
			m_PurgeConfirmParentNetId = "";
		}
		int i = 0;
		while (i < m_PendingFinishIds.Count())
		{
			if (m_PendingFinishIds.Get(i) == job_id)
			{
				m_PendingFinishIds.RemoveOrdered(i);
				m_PendingFinishTicks.RemoveOrdered(i);
				m_PendingFinishSeen.RemoveOrdered(i);
				m_PendingFinishAgeMs.RemoveOrdered(i);
				return;
			}
			i = i + 1;
		}
	}

	protected bool IsQaIdentity(string netId, string persId, array<string> netIds, array<string> persIds)
	{
		// BLOQ 5: una identidad vacia o cero (0:0 / 0:0:0:0) nunca coincide,
		// ni como candidata ni como entrada registrada.
		if (IsValidIdentity(netId, "0:0"))
		{
			for (int i = 0; i < netIds.Count(); i++)
			{
				if (IsValidIdentity(netIds.Get(i), "0:0") && netIds.Get(i) == netId)
					return true;
			}
		}
		if (IsValidIdentity(persId, "0:0:0:0"))
		{
			for (int j = 0; j < persIds.Count(); j++)
			{
				if (IsValidIdentity(persIds.Get(j), "0:0:0:0") && persIds.Get(j) == persId)
					return true;
			}
		}
		return false;
	}

	protected bool IsQaHealthMark(Object obj)
	{
		EntityAI ent = EntityAI.Cast(obj);
		if (!ent)
			return false;
		float maxHp = -1.0;
		float hp = -1.0;
		ReadQaHealth(ent, maxHp, hp);
		if (maxHp <= 0.0)
			return false;
		float d1 = hp - maxHp * 0.7325;
		if (d1 < 0.0)
			d1 = -d1;
		if (d1 <= 1e-2)
			return true;
		float d2 = hp - maxHp * 0.6150;
		if (d2 < 0.0)
			d2 = -d2;
		if (d2 <= 1e-2)
			return true;
		float d3 = hp - maxHp * 0.8450;
		if (d3 < 0.0)
			d3 = -d3;
		return d3 <= 1e-2;
	}

	protected void CleanupAllEntities(DSBX_QA_Args args, out int cleanedOwnN, out int cleanedRawN)
	{
		cleanedOwnN = 0;
		cleanedRawN = 0;
		// MEN 5: t6 solo excluye el inventario del director; los actores de la escena
		// y sus prendas se borran como antes (no se salta cualquier Man).
		string cleanupDirUid = "";
		int cleanupPlayersN = 0;
		int cleanupPresentB = 0;
		int cleanupAliveB = 0;
		int cleanupInvReadableB = 0;
		int cleanupInvCountN = 0;
		Man cleanupDirector = null;
		// Si la purga fijo al director, se usa su uid; si no, el uid que manda el
		// runner; y si tampoco, el unico jugador listo.
		string cleanupWantedUid = m_PurgeDirectorUid;
		if (cleanupWantedUid == "")
			cleanupWantedUid = GetStrArg(args, "director_uid", "");
		if (cleanupWantedUid != "")
			cleanupDirector = FindPlayerByUid(cleanupWantedUid, cleanupDirUid, cleanupPresentB, cleanupAliveB, cleanupInvReadableB, cleanupInvCountN);
		else
			cleanupDirector = FindOnlyPlayer(cleanupDirUid, cleanupPlayersN, cleanupPresentB, cleanupAliveB, cleanupInvReadableB, cleanupInvCountN);

		array<string> qaNetIds = new array<string>();
		array<string> qaPersIds = new array<string>();
		for (int q = 0; q < m_Records.Count(); q++)
		{
			DSBX_QA_PersistRecord qrec = m_Records.Get(q);
			if (!qrec)
				continue;
			if (IsValidIdentity(qrec.m_NetId, "0:0"))
				qaNetIds.Insert(qrec.m_NetId);
			if (IsValidIdentity(qrec.m_PersId, "0:0:0:0"))
				qaPersIds.Insert(qrec.m_PersId);
		}
		for (int qr = 0; qr < m_RawRecords.Count(); qr++)
		{
			DSBX_QA_PersistRawRecord qraw = m_RawRecords.Get(qr);
			if (!qraw)
				continue;
			if (IsValidIdentity(qraw.m_NetId, "0:0"))
				qaNetIds.Insert(qraw.m_NetId);
			if (IsValidIdentity(qraw.m_PersId, "0:0:0:0"))
				qaPersIds.Insert(qraw.m_PersId);
			if (IsObjectAlive(qraw.m_ChildEnt))
			{
				string childNet = FormatNetId(qraw.m_ChildEnt);
				if (IsValidIdentity(childNet, "0:0"))
					qaNetIds.Insert(childNet);
			}
		}

		for (int i = m_Records.Count() - 1; i >= 0; i--)
		{
			DSBX_QA_PersistRecord rec = m_Records.Get(i);
			// MEN 5: t6 no toca el inventario del director (conserva lo suyo); el de
			// los actores de la escena si se borra.
			EntityAI recEnt = null;
			if (rec)
				recEnt = EntityAI.Cast(rec.m_RefEnt);
			if (recEnt && cleanupDirector && recEnt.GetHierarchyRootPlayer() == cleanupDirector)
				continue;
			// BLOQ 5: un contenedor registrado con descendientes ajenos o
			// desconocidos no se borra (como al reaplicar); se conserva.
			if (rec && IsObjectAlive(rec.m_RefEnt) && CountCleanupForeignDescendants(rec.m_RefEnt) > 0)
				continue;
			if (rec && IsObjectAlive(rec.m_RefEnt))
			{
				g_Game.ObjectDelete(rec.m_RefEnt);
				cleanedOwnN = cleanedOwnN + 1;
			}
			if (rec)
				rec.m_RefEnt = null;
			m_Records.RemoveOrdered(i);
		}

		for (int s = m_SceneIds.Count() - 1; s >= 0; s--)
		{
			m_SceneIds.RemoveOrdered(s);
			m_SceneGen.RemoveOrdered(s);
			m_SceneLastOp.RemoveOrdered(s);
			m_SceneLastRetainedSkipped.RemoveOrdered(s);
		}

		for (int j = m_RawRecords.Count() - 1; j >= 0; j--)
		{
			DSBX_QA_PersistRawRecord raw = m_RawRecords.Get(j);
			if (raw)
			{
				// BLOQ 5: tampoco un raw con descendientes desconocidos.
				if (IsObjectAlive(raw.m_RefEnt) && CountCleanupForeignDescendants(raw.m_RefEnt) > 0)
					continue;
				if (IsObjectAlive(raw.m_ChildEnt))
					g_Game.ObjectDelete(raw.m_ChildEnt);
				if (IsObjectAlive(raw.m_RefEnt))
				{
					g_Game.ObjectDelete(raw.m_RefEnt);
					cleanedRawN = cleanedRawN + 1;
				}
				raw.m_RefEnt = null;
				raw.m_ChildEnt = null;
			}
			m_RawRecords.RemoveOrdered(j);
		}

		if (args && args.rows > 0)
		{
			int ncolCount = args.ncol.Count();
			int idxCx = FindColIdx(args.ncol, "center_x_m");
			int idxCz = FindColIdx(args.ncol, "center_z_m");
			int idxRad = FindColIdx(args.ncol, "radius_m");
			for (int r = 0; r < args.rows; r++)
			{
				int nBase = r * ncolCount;
				float cx = args.ncell.Get(nBase + idxCx);
				float cz = args.ncell.Get(nBase + idxCz);
				float rad = args.ncell.Get(nBase + idxRad);
				vector cPos = Vector(cx, g_Game.SurfaceY(cx, cz), cz);
				array<Object> nearObjs = new array<Object>();
				array<CargoBase> nearCargos = new array<CargoBase>();
				g_Game.GetObjectsAtPosition3D(cPos, rad, nearObjs, nearCargos);
				for (int k = 0; k < nearObjs.Count(); k++)
				{
					Object cand = nearObjs.Get(k);
					if (!IsObjectAlive(cand))
						continue;
					EntityAI ent = EntityAI.Cast(cand);
					if (!ent)
						continue;
					// MEN 5: solo se protege al director y su inventario; un actor de
					// la escena (otro Man) y sus prendas se borran.
					if (cleanupDirector && ent == cleanupDirector)
						continue;
					if (cleanupDirector && ent.GetHierarchyRootPlayer() == cleanupDirector)
						continue;
					bool byIdentity = IsQaIdentity(FormatNetId(cand), FormatPersId(cand), qaNetIds, qaPersIds);
					bool byMark = IsSentinelClass(cand.GetType()) && IsQaHealthMark(cand);
					if ((byIdentity || byMark) && CountCleanupForeignDescendants(cand) == 0)
					{
						g_Game.ObjectDelete(cand);
						cleanedRawN = cleanedRawN + 1;
					}
				}
			}
		}
	}

	protected void HandleCleanupQA(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		int cleanedOwnN = 0;
		int cleanedRawN = 0;
		CleanupAllEntities(args, cleanedOwnN, cleanedRawN);

		res.status = "done";
		EnsurePayloadHas(res.read);
		PutNum(res.read, "cleaned_own_n", cleanedOwnN);
		PutNum(res.read, "cleaned_raw_n", cleanedRawN);
		PutNum(res.read, "tick_ms", m_Probe.NowMs());
		PutNum(res.read, "frame", m_Probe.m_Frame);
	}

	override void OnRpc(PlayerIdentity sender, Object target, int rpc_type, ParamsReadContext ctx)
	{
	}

	override void OnShutdown()
	{
		// Cualquier final apaga el testigo, tambien el apagado del servidor.
		ResetWitness();
		// La base tiene que sobrevivir al reinicio de t4, y la limpieza la hacen t6 y la restauracion en frio.
	}
}
