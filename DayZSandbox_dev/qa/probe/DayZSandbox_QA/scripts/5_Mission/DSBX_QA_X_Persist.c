// DSBX_QA_X_Persist.c — S-persist server-only extension (F0.3b).
// Handles verbs with prefix "per_" on role == "server".
// Ordered arrays (m_Records, m_SceneIds, m_SceneGen, m_SceneLastOp, m_RawRecords)
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
	protected string m_PendingFinishJobId;

	void DSBX_QA_X_Persist()
	{
		m_Records = new array<ref DSBX_QA_PersistRecord>();
		m_SceneIds = new array<string>();
		m_SceneGen = new array<int>();
		m_SceneLastOp = new array<string>();
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
		m_PendingFinishJobId = "";

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

	protected Man FindDirectorMan(out string directorUid, out int presentB, out int aliveB, out int invReadableB, out int invCountN)
	{
		directorUid = "";
		presentB = 0;
		aliveB = 0;
		invReadableB = 0;
		invCountN = 0;
		array<Man> players = new array<Man>();
		g_Game.GetPlayers(players);
		if (!players || players.Count() == 0)
			return null;
		Man dir = players.Get(0);
		if (!dir)
			return null;
		presentB = 1;
		if (dir.IsAlive())
			aliveB = 1;
		PlayerIdentity ident = dir.GetIdentity();
		if (ident)
			directorUid = ident.GetId();
		EntityAI dirEnt = EntityAI.Cast(dir);
		if (dirEnt && dirEnt.GetInventory())
		{
			invReadableB = 1;
			array<EntityAI> items = new array<EntityAI>();
			dirEnt.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, items);
			int cnt = 0;
			for (int i = 0; i < items.Count(); i++)
			{
				if (items.Get(i) != dirEnt)
					cnt = cnt + 1;
			}
			invCountN = cnt;
		}
		return dir;
	}

	protected void ReadRealLocation(Object obj, Man director, string directorUid, out string locKind, out string parentClass, out string parentNetId, out string slotName, out string ownerUid, out int invChildrenN, bool proxyAsCargo = false)
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
			int chCnt = 0;
			for (int i = 0; i < children.Count(); i++)
			{
				if (children.Get(i) != ent)
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

	override void OnStartOp(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string verb = op.verb;
		if (verb == "per_cleanup_qa")
		{
			HandleCleanupQA(op, args, res);
			return;
		}

		if (!m_Probe || !m_Probe.LeaseOk())
		{
			res.status = "error";
			res.reason = "lease_expired";
			return;
		}

		if (verb == "per_status")
		{
			HandleStatus(op, args, res);
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
		string directorUid = "";
		int presentB = 0;
		int aliveB = 0;
		int invReadableB = 0;
		int invCountN = 0;
		FindDirectorMan(directorUid, presentB, aliveB, invReadableB, invCountN);

		res.status = "done";
		EnsurePayloadHas(res.read);
		PutStr(res.read, "server_epoch", m_Probe.GetInst());
		PutStr(res.read, "director_uid", directorUid);

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

		int rootsN = 0;
		int childrenN = 0;
		int rowCount = 0;
		for (int i = 0; i < m_Records.Count(); i++)
		{
			DSBX_QA_PersistRecord r = m_Records.Get(i);
			if (!r || r.m_SceneId != sceneId || r.m_GenN != genN)
				continue;
			rowCount = rowCount + 1;
			if (r.m_ParentId == "")
				rootsN = rootsN + 1;
			else
				childrenN = childrenN + 1;

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
		}
		read.rows = rowCount;

		PutStr(read, "apply_status", "ok");
		PutStr(read, "reason", "");
		PutStr(read, "server_epoch", m_Probe.GetInst());
		PutStr(read, "scene_id", sceneId);
		PutStr(read, "scene_op_id", sceneOpId);
		PutStr(read, "q9_pathway", pathway);

		PutNum(read, "gen_n", genN);
		PutNum(read, "created_roots_n", rootsN);
		PutNum(read, "created_children_n", childrenN);
		PutNum(read, "idempotent_hit_b", idempotentHitB);
		PutNum(read, "q9_tick_ms", m_Probe.NowMs());
		PutNum(read, "q9_frame", m_Probe.m_Frame);
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
			res.status = "rejected";
			res.reason = "stale_epoch";
			return;
		}
		if (pathway != "a" && pathway != "b")
		{
			res.status = "rejected";
			res.reason = "bad_args";
			return;
		}
		if (sceneId == "" || sceneOpId == "" || genN < 1)
		{
			res.status = "rejected";
			res.reason = "bad_args";
			return;
		}

		int scIdx = FindSceneIndex(sceneId);
		if (scIdx >= 0 && m_SceneLastOp.Get(scIdx) == sceneOpId)
		{
			res.status = "done";
			EmitApplyResponse(res.read, sceneId, sceneOpId, pathway, m_SceneGen.Get(scIdx), 1);
			return;
		}

		int rows = 0;
		if (args && args.rows > 0)
			rows = args.rows;
		if (rows < 1 || rows > 12)
		{
			res.status = "rejected";
			res.reason = "bad_args";
			return;
		}

		for (int d = m_Records.Count() - 1; d >= 0; d--)
		{
			DSBX_QA_PersistRecord oldRec = m_Records.Get(d);
			if (oldRec && oldRec.m_SceneId == sceneId)
			{
				if (IsObjectAlive(oldRec.m_RefEnt))
				{
					g_Game.ObjectDelete(oldRec.m_RefEnt);
				}
				oldRec.m_RefEnt = null;
				m_Records.RemoveOrdered(d);
			}
		}

		UpsertSceneMeta(sceneId, genN, sceneOpId);

		int ncolCount = args.ncol.Count();
		int scolCount = args.scol.Count();

		int idxLogical = FindColIdx(args.scol, "logical_id");
		int idxParent = FindColIdx(args.scol, "parent_id");
		int idxCat = FindColIdx(args.scol, "cat");
		int idxClass = FindColIdx(args.scol, "class_name");
		int idxSlot = FindColIdx(args.scol, "slot_name");

		int idxReqX = FindColIdx(args.ncol, "req_x_m");
		int idxReqZ = FindColIdx(args.ncol, "req_z_m");
		int idxReqYaw = FindColIdx(args.ncol, "req_yaw_deg");
		int idxHealthRatio = FindColIdx(args.ncol, "health_mark_ratio");
		int idxMustVanish = FindColIdx(args.ncol, "must_vanish_b");

		string opFault = m_Probe.GetOpFault();
		bool omitNoPersist = (opFault == "omit_nopersistency_flag");

		string directorUid = "";
		int presentB = 0;
		int dirAliveB = 0;
		int invReadableB = 0;
		int invCountN = 0;
		Man director = FindDirectorMan(directorUid, presentB, dirAliveB, invReadableB, invCountN);

		for (int r = 0; r < rows; r++)
		{
			int sBase = r * scolCount;
			int nBase = r * ncolCount;

			string logicalId = args.scell.Get(sBase + idxLogical);
			string parentId = args.scell.Get(sBase + idxParent);
			string cat = args.scell.Get(sBase + idxCat);
			string className = args.scell.Get(sBase + idxClass);
			string slotName = args.scell.Get(sBase + idxSlot);

			float reqX = args.ncell.Get(nBase + idxReqX);
			float reqZ = args.ncell.Get(nBase + idxReqZ);
			float reqYaw = args.ncell.Get(nBase + idxReqYaw);
			float hRatio = args.ncell.Get(nBase + idxHealthRatio);
			int mustVanishB = (int)args.ncell.Get(nBase + idxMustVanish);

			Object createdObj = null;
			float reqY = g_Game.SurfaceY(reqX, reqZ);
			vector targetPos = Vector(reqX, reqY, reqZ);

			if (parentId == "")
			{
				int flags = FLAGS_STATIC;
				if (cat == "infected" || cat == "animal")
				{
					if (pathway == "a")
						flags = FLAGS_AI_A;
					else
						flags = FLAGS_AI_B;
				}
				if (omitNoPersist)
				{
					flags = flags & (~FLAG_ECE_NOPERSISTENCY_WORLD);
				}
				createdObj = g_Game.CreateObjectEx(className, targetPos, flags, FLAG_RF_DEFAULT);
				if (createdObj)
				{
					createdObj.SetPosition(targetPos);
					createdObj.SetOrientation(Vector(reqYaw, 0.0, 0.0));
				}
			}
			else
			{
				DSBX_QA_PersistRecord parentRec = FindRecord(sceneId, parentId);
				if (parentRec && parentRec.m_RefEnt)
				{
					EntityAI parentEnt = EntityAI.Cast(parentRec.m_RefEnt);
					if (parentEnt && parentEnt.GetInventory())
					{
						InventoryLocation invLoc = new InventoryLocation();
						if (slotName == "Cargo")
						{
							if (parentEnt.GetInventory().FindFirstFreeLocationForNewEntity(className, FindInventoryLocationType.CARGO, invLoc))
							{
								createdObj = GameInventory.LocationCreateEntity(invLoc, className, FLAGS_INV_OWN, FLAG_RF_DEFAULT);
							}
						}
						else
						{
							int slotId = InventorySlots.GetSlotIdFromString(slotName);
							if (InventorySlots.IsSlotIdValid(slotId) && parentEnt.GetInventory().HasAttachmentSlot(slotId) && parentEnt.GetInventory().FindAttachment(slotId) == null)
							{
								invLoc.SetAttachment(parentEnt, null, slotId);
								createdObj = GameInventory.LocationCreateEntity(invLoc, className, FLAGS_INV_OWN, FLAG_RF_DEFAULT);
							}
						}
					}
				}
			}

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
			rec.m_SpawnTickMs = m_Probe.NowMs();
			rec.m_RefEnt = createdObj;

			if (createdObj)
			{
				rec.m_OkB = 1;
				EntityAI ent = EntityAI.Cast(createdObj);
				if (ent)
				{
					float maxHp = ent.GetMaxHealth("", "");
					if (maxHp > 0.0 && hRatio > 0.0)
					{
						ent.SetHealth("", "", maxHp * hRatio);
					}
					rec.m_MaxHp = maxHp;
					rec.m_HealthHp = ent.GetHealth("", "");
				}
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

				if (cat == "infected" || cat == "animal")
				{
					DayZCreatureAI creature = DayZCreatureAI.Cast(createdObj);
					if (pathway == "b" && creature)
					{
						creature.InitAIAgent(g_Game.GetWorld().GetAIWorld().CreateDefaultGroup());
					}
					if (creature && creature.GetAIAgent() != null)
					{
						rec.m_AiAgentB = 1;
					}
				}

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
			m_Records.Insert(rec);
		}

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

		string directorUid = "";
		int presentB = 0;
		int aliveB = 0;
		int invReadableB = 0;
		int invCountN = 0;
		Man director = FindDirectorMan(directorUid, presentB, aliveB, invReadableB, invCountN);

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

		bool moveOk = false;
		if (action == "drop_to_ground")
		{
			EntityAI curOwner = itemEnt.GetHierarchyParent();
			if (curOwner && curOwner.GetInventory())
			{
				moveOk = curOwner.GetInventory().DropEntity(InventoryMode.SERVER, curOwner, itemEnt);
			}
		}
		else if (action == "move_to_director")
		{
			EntityAI dirEnt = EntityAI.Cast(director);
			if (dirEnt && dirEnt.GetInventory())
			{
				moveOk = dirEnt.GetInventory().TakeEntityToInventory(InventoryMode.SERVER, FindInventoryLocationType.ANY, itemEnt);
			}
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

	protected void HandleSpawnRaw(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string tag = GetStrArg(args, "tag", "");
		string mode = GetStrArg(args, "mode", "");
		string className = GetStrArg(args, "class_name", "");
		string childCargoClass = GetStrArg(args, "child_cargo_class", "");
		string targetSceneId = GetStrArg(args, "target_scene_id", "");
		string targetParentId = GetStrArg(args, "target_parent_id", "");
		string targetNetId = GetStrArg(args, "target_net_id", "");

		float xm = GetNumArg(args, "x_m", 0.0);
		float zm = GetNumArg(args, "z_m", 0.0);
		float yawDeg = GetNumArg(args, "yaw_deg", 0.0);
		float hRatio = GetNumArg(args, "health_mark_ratio", 1.0);

		Object createdObj = null;
		Object childObj = null;
		int childCountN = 0;
		float ym = g_Game.SurfaceY(xm, zm);
		vector targetPos = Vector(xm, ym, zm);

		if (mode == "foreign_ground")
		{
			createdObj = g_Game.CreateObjectEx(className, targetPos, FLAGS_STATIC, FLAG_RF_DEFAULT);
			if (createdObj)
			{
				createdObj.SetPosition(targetPos);
				createdObj.SetOrientation(Vector(yawDeg, 0.0, 0.0));
			}
		}
		else if (mode == "foreign_in_container" && targetNetId != "")
		{
			// Padre por net_id del censo. Los dos rechazos salen antes de crear nada (sin efectos).
			int tHigh = 0;
			int tLow = 0;
			if (!ParseNetIdStr(targetNetId, tHigh, tLow))
			{
				res.status = "rejected";
				res.reason = "bad_args";
				return;
			}
			// GetObjectByNetworkId(low, high): P:/scripts/3_game/global/game.c:356
			EntityAI netParEnt = EntityAI.Cast(g_Game.GetObjectByNetworkId(tLow, tHigh));
			if (!netParEnt || !IsObjectAlive(netParEnt))
			{
				res.status = "rejected";
				res.reason = "target_not_found";
				return;
			}
			// FindFirstFreeLocationForNewEntity: inventory.c:291; LocationCreateEntity: inventory.c:333
			InventoryLocation netLoc = new InventoryLocation();
			if (!netParEnt.GetInventory() || !netParEnt.GetInventory().FindFirstFreeLocationForNewEntity(className, FindInventoryLocationType.CARGO, netLoc))
			{
				res.status = "rejected";
				res.reason = "no_cargo_space";
				return;
			}
			// La busqueda puede dar hueco en el cargo de un descendiente (vanilla usa el padre devuelto, inventory.c:879):
			// el hueco tiene que ser CARGO y el padre de la ubicacion exactamente el objetivo; si no, sin efectos.
			// InventoryLocation.GetType/GetParent: inventorylocation.c:43 y :52.
			if (netLoc.GetType() != InventoryLocationType.CARGO || netLoc.GetParent() != netParEnt)
			{
				res.status = "rejected";
				res.reason = "no_cargo_space";
				return;
			}
			createdObj = GameInventory.LocationCreateEntity(netLoc, className, FLAG_ECE_IN_INVENTORY, FLAG_RF_DEFAULT);
		}
		else if (mode == "foreign_in_container")
		{
			DSBX_QA_PersistRecord parRec = FindRecord(targetSceneId, targetParentId);
			if (parRec && IsObjectAlive(parRec.m_RefEnt))
			{
				EntityAI parEnt = EntityAI.Cast(parRec.m_RefEnt);
				if (parEnt && parEnt.GetInventory())
				{
					InventoryLocation invLoc = new InventoryLocation();
					if (parEnt.GetInventory().FindFirstFreeLocationForNewEntity(className, FindInventoryLocationType.CARGO, invLoc))
					{
						createdObj = GameInventory.LocationCreateEntity(invLoc, className, FLAG_ECE_IN_INVENTORY, FLAG_RF_DEFAULT);
					}
				}
			}
		}
		else if (mode == "persistent_control")
		{
			createdObj = g_Game.CreateObjectEx(className, targetPos, FLAG_ECE_PLACE_ON_SURFACE, FLAG_RF_DEFAULT);
			if (createdObj)
			{
				createdObj.SetPosition(targetPos);
				createdObj.SetOrientation(Vector(yawDeg, 0.0, 0.0));
				if (childCargoClass != "")
				{
					EntityAI ctrlEnt = EntityAI.Cast(createdObj);
					if (ctrlEnt && ctrlEnt.GetInventory())
					{
						InventoryLocation chLoc = new InventoryLocation();
						if (ctrlEnt.GetInventory().FindFirstFreeLocationForNewEntity(childCargoClass, FindInventoryLocationType.CARGO, chLoc))
						{
							childObj = GameInventory.LocationCreateEntity(chLoc, childCargoClass, FLAG_ECE_IN_INVENTORY, FLAG_RF_DEFAULT);
							if (childObj)
								childCountN = 1;
						}
					}
				}
			}
		}

		if (!createdObj)
		{
			res.status = "error";
			res.reason = "spawn_failed";
			return;
		}

		float maxHp = 100.0;
		float healthHp = 100.0;
		EntityAI cEnt = EntityAI.Cast(createdObj);
		if (cEnt)
		{
			maxHp = cEnt.GetMaxHealth("", "");
			if (maxHp > 0.0 && hRatio > 0.0)
			{
				cEnt.SetHealth("", "", maxHp * hRatio);
			}
			healthHp = cEnt.GetHealth("", "");
		}

		string directorUid = "";
		int presentB = 0;
		int aliveB = 0;
		int invReadableB = 0;
		int invCountN = 0;
		Man director = FindDirectorMan(directorUid, presentB, aliveB, invReadableB, invCountN);

		string obsLocKind = "";
		string obsParentClass = "";
		string obsParentNetId = "";
		string obsSlotName = "";
		string obsOwnerUid = "";
		int invChildren = 0;
		ReadRealLocation(createdObj, director, directorUid, obsLocKind, obsParentClass, obsParentNetId, obsSlotName, obsOwnerUid, invChildren);

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
	}

	protected void AppendEntityCensusRow(string jobId, Object obj, int inRadiusB, Man director, string directorUid, array<Object> seen, bool withSurface)
	{
		if (!IsObjectAlive(obj))
			return;
		for (int s = 0; s < seen.Count(); s++)
		{
			if (seen.Get(s) == obj)
				return;
		}
		seen.Insert(obj);

		string className = obj.GetType();
		string locKind = "";
		string parentClass = "";
		string parentNetId = "";
		string slotName = "";
		string ownerUid = "";
		int invChildrenN = 0;
		ReadRealLocation(obj, director, directorUid, locKind, parentClass, parentNetId, slotName, ownerUid, invChildrenN, withSurface);

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
		EntityAI ent = EntityAI.Cast(obj);
		if (ent)
		{
			maxHp = ent.GetMaxHealth("", "");
			healthHp = ent.GetHealth("", "");
		}

		array<string> svals = new array<string>();
		svals.Insert(className);
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
		if (withSurface)
		{
			// surface_y_m, la ultima columna y solo con select_all_entityai_b = 1: SurfaceY (game.c:1176)
			nvals.Insert(g_Game.SurfaceY(pos[0], pos[2]));
		}

		m_Jobs.AppendRow(jobId, nvals, svals);
	}

	protected void HandleCensusStart(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string areaTag = GetStrArg(args, "area_tag", "");
		float centerX = GetNumArg(args, "center_x_m", 0.0);
		float centerZ = GetNumArg(args, "center_z_m", 0.0);
		float radiusM = GetNumArg(args, "radius_m", 60.0);
		int includeDirectorB = (int)GetNumArg(args, "include_director_b", 0.0);

		// Modo opt-in select_all_entityai_b (0 o 1, por defecto 0). Con 0 nada de lo de abajo cambia: ni filas, ni columnas,
		// ni tope de radio (S-persist usa discos grandes). Con 1 el radio tiene que estar en (0, 120]; los rechazos salen
		// antes de StartJob y de cualquier efecto.
		float selectAllRaw = GetNumArg(args, "select_all_entityai_b", 0.0);
		if (selectAllRaw != 0.0 && selectAllRaw != 1.0)
		{
			res.status = "rejected";
			res.reason = "bad_args";
			return;
		}
		int selectAllB = (int)selectAllRaw;
		if (selectAllB == 1 && (radiusM <= 0.0 || radiusM > CENSUS_ALL_RADIUS_MAX))
		{
			res.status = "rejected";
			res.reason = "bad_args";
			return;
		}
		array<string> censusNcol = m_CensusNcol;
		if (selectAllB == 1)
			censusNcol = m_CensusNcolAll;

		string err = m_Jobs.StartJob(this, op.op_id, "per_census", censusNcol, m_CensusScol, 5, 4096, 900000.0, "stop");
		if (err != "")
		{
			res.status = "rejected";
			res.reason = err;
			return;
		}
		DSBX_QA_Job job = m_Jobs.GetJob(op.op_id);
		if (job)
		{
			job.m_ExtHandlesDeadman = true;
		}

		string opFault = m_Probe.GetOpFault();
		if (opFault == "drop_ctrl_pre_restart")
		{
			for (int d = m_RawRecords.Count() - 1; d >= 0; d--)
			{
				DSBX_QA_PersistRawRecord rraw = m_RawRecords.Get(d);
				if (rraw && rraw.m_Mode == "persistent_control")
				{
					if (IsObjectAlive(rraw.m_ChildEnt))
						g_Game.ObjectDelete(rraw.m_ChildEnt);
					if (IsObjectAlive(rraw.m_RefEnt))
						g_Game.ObjectDelete(rraw.m_RefEnt);
					m_RawRecords.RemoveOrdered(d);
				}
			}
		}

		string directorUid = "";
		int presentB = 0;
		int aliveB = 0;
		int invReadableB = 0;
		int invCountN = 0;
		Man director = FindDirectorMan(directorUid, presentB, aliveB, invReadableB, invCountN);

		array<Object> seen = new array<Object>();
		vector centerPos = Vector(centerX, g_Game.SurfaceY(centerX, centerZ), centerZ);
		array<Object> nearObjs = new array<Object>();
		array<CargoBase> nearCargos = new array<CargoBase>();
		g_Game.GetObjectsAtPosition3D(centerPos, radiusM, nearObjs, nearCargos);

		for (int i = 0; i < nearObjs.Count(); i++)
		{
			Object obj = nearObjs.Get(i);
			if (!IsObjectAlive(obj))
				continue;
			if (director && obj == director)
				continue;
			string cname = obj.GetType();
			bool includeObj = false;
			if (selectAllB == 1)
			{
				// Todo EntityAI del disco; lo que no es EntityAI (arboles, rocas) queda fuera.
				if (EntityAI.Cast(obj) != null)
					includeObj = true;
				// Con el tope de filas ya cumplido el trabajo esta en failed/rows_cap: no se sigue recorriendo.
				if (m_Jobs.GetState(op.op_id) != "running")
					break;
			}
			else if (FindRecordByObject(obj) != null)
				includeObj = true;
			else if (IsSentinelClass(cname))
				includeObj = true;
			else if (DayZCreatureAI.Cast(obj) != null)
				includeObj = true;

			if (!includeObj)
				continue;

			AppendEntityCensusRow(op.op_id, obj, 1, director, directorUid, seen, selectAllB == 1);
			EntityAI ent = EntityAI.Cast(obj);
			if (ent && ent.GetInventory())
			{
				array<EntityAI> subItems = new array<EntityAI>();
				ent.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, subItems);
				for (int sub = 0; sub < subItems.Count(); sub++)
				{
					EntityAI subEnt = subItems.Get(sub);
					if (subEnt && subEnt != ent)
					{
						AppendEntityCensusRow(op.op_id, subEnt, 1, director, directorUid, seen, selectAllB == 1);
					}
				}
			}
		}

		// Las criaturas propias que salieron del disco solo cuentan en el modo de S-persist (m_Records no pinta nada
		// en el modo select_all_entityai_b).
		int recLimit = m_Records.Count();
		if (selectAllB == 1)
			recLimit = 0;
		for (int r = 0; r < recLimit; r++)
		{
			DSBX_QA_PersistRecord rec = m_Records.Get(r);
			if (!rec || !IsObjectAlive(rec.m_RefEnt))
				continue;
			if (rec.m_Cat != "infected" && rec.m_Cat != "animal")
				continue;
			float dx = rec.m_ReqXM - centerX;
			float dz = rec.m_ReqZM - centerZ;
			if ((dx * dx + dz * dz) <= (radiusM * radiusM))
			{
				AppendEntityCensusRow(op.op_id, rec.m_RefEnt, 0, director, directorUid, seen, selectAllB == 1);
			}
		}

		if (includeDirectorB != 0 && director)
		{
			EntityAI dirEnt = EntityAI.Cast(director);
			if (dirEnt && dirEnt.GetInventory())
			{
				array<EntityAI> dirItems = new array<EntityAI>();
				dirEnt.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, dirItems);
				for (int di = 0; di < dirItems.Count(); di++)
				{
					EntityAI dItem = dirItems.Get(di);
					if (dItem && dItem != dirEnt)
					{
						AppendEntityCensusRow(op.op_id, dItem, 1, director, directorUid, seen, selectAllB == 1);
					}
				}
			}
		}

		m_PendingFinishJobId = op.op_id;
		res.status = "done";
		m_Jobs.FillStartRead(res.read, op.op_id, "per_census");
		PutStr(res.read, "area_tag", areaTag);
		PutStr(res.read, "server_epoch", m_Probe.GetInst());
		PutStr(res.read, "director_uid", directorUid);

		PutNum(res.read, "snap_tick_ms", m_Probe.NowMs());
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

	// ---------------------------------------------------------------- creation witness (per_witness_start)
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

		// 1) Capturas de EEInit acumuladas desde el tick anterior (sample_idx 0). Se incorporan ANTES del seguimiento: su
		//    sample_idx 1 sale en este mismo tick, el frame siguiente al de EEInit (frames consecutivos 0, 1, ..., K).
		int capN = DSBX_QA_Witness.s_Buf.Count();
		for (int c = 0; c < capN; c++)
		{
			DSBX_QA_WitnessCapture cap = DSBX_QA_Witness.s_Buf.Get(c);
			if (!cap)
				continue;
			if (!AppendWitnessRow(jid, 0, cap.m_ClassName, cap.m_NetId, cap.m_ParentNetId, cap.m_PosX, cap.m_PosY, cap.m_PosZ, cap.m_YawDeg, cap.m_TickMs, cap.m_Frame, cap.m_AiAgentB, 1))
				return;
			DSBX_QA_PersistWitnessFollow nf = new DSBX_QA_PersistWitnessFollow();
			nf.m_Ent = cap.m_Ent;
			nf.m_ClassName = cap.m_ClassName;
			nf.m_NetId = cap.m_NetId;
			nf.m_ParentNetId = cap.m_ParentNetId;
			nf.m_LastX = cap.m_PosX;
			nf.m_LastY = cap.m_PosY;
			nf.m_LastZ = cap.m_PosZ;
			nf.m_LastYawDeg = cap.m_YawDeg;
			nf.m_NextSample = 1;
			m_WitnessFollow.Insert(nf);
		}
		DSBX_QA_Witness.s_Buf.Clear();

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
		if (m_PendingFinishJobId == "")
			return;
		string jid = m_PendingFinishJobId;
		m_PendingFinishJobId = "";
		if (m_Jobs.IsDeadmanTripped(jid))
		{
			m_Jobs.EndJob(jid, "failed", "lease_expired");
			return;
		}
		m_Jobs.EndJob(jid, "done", "");
	}

	override void OnJobEnd(string job_id, string state, string reason)
	{
		if (m_PendingFinishJobId == job_id)
		{
			m_PendingFinishJobId = "";
		}
		// Cualquier final del trabajo (done, rows_cap, lease_expired, job_timeout, shutdown) apaga el gancho.
		if (m_WitnessJobId == job_id)
		{
			ResetWitness();
		}
	}

	protected void CleanupAllEntities(DSBX_QA_Args args, out int cleanedOwnN, out int cleanedRawN)
	{
		cleanedOwnN = 0;
		cleanedRawN = 0;

		for (int i = m_Records.Count() - 1; i >= 0; i--)
		{
			DSBX_QA_PersistRecord rec = m_Records.Get(i);
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
		}

		for (int j = m_RawRecords.Count() - 1; j >= 0; j--)
		{
			DSBX_QA_PersistRawRecord raw = m_RawRecords.Get(j);
			if (raw)
			{
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
					if (!ent || ent.IsMan())
						continue;
					if (IsSentinelClass(cand.GetType()))
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
		ResetWitness();
		int cleanedOwnN = 0;
		int cleanedRawN = 0;
		CleanupAllEntities(null, cleanedOwnN, cleanedRawN);
	}
}
