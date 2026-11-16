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
	protected ref array<string> m_PendingFinishIds;
	protected ref array<int> m_PendingFinishTicks;
	protected ref array<int> m_PendingFinishSeen;
	protected ref array<float> m_PendingFinishAgeMs;
	protected float m_CensusCaptureStartMs;
	protected bool m_CaptureFailed;
	protected string m_CaptureFailReason;
	protected string m_CaptureFailJobId;
	protected int m_LastApplyRetainedSkipped;
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
		m_RawRecords = new array<ref DSBX_QA_PersistRawRecord>();
		m_SentinelClasses = new array<string>();
		m_CensusNcol = new array<string>();
		m_CensusScol = new array<string>();
		m_PendingFinishIds = new array<string>();
		m_PendingFinishTicks = new array<int>();
		m_PendingFinishSeen = new array<int>();
		m_PendingFinishAgeMs = new array<float>();
		m_CensusCaptureStartMs = 0.0;
		m_CaptureFailed = false;
		m_CaptureFailReason = "";
		m_CaptureFailJobId = "";
		m_LastApplyRetainedSkipped = 0;

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

	protected void ReadRealLocation(Object obj, Man director, string directorUid, out string locKind, out string parentClass, out string parentNetId, out string slotName, out string ownerUid, out int invChildrenN)
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
			if (!FindRecordByObject(child) && !FindRawRecordByObject(child))
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
		if (verb == "per_census_start")
		{
			HandleCensusStart(op, args, res);
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
			m_LastApplyRetainedSkipped = 0;
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

		if (idxLogical < 0 || idxParent < 0 || idxCat < 0 || idxClass < 0 || idxSlot < 0 || idxReqX < 0 || idxReqZ < 0 || idxReqYaw < 0 || idxHealthRatio < 0 || idxMustVanish < 0)
		{
			res.status = "rejected";
			res.reason = "bad_args";
			return;
		}

		if (!ReapplyResetWithRetention(sceneId, expectEpoch))
		{
			res.status = "error";
			res.reason = "lease_expired";
			return;
		}
		// MEN 7: logical_ids retenidos de la generacion anterior.
		array<string> retainedLids = new array<string>();
		for (int ri = 0; ri < m_Records.Count(); ri++)
		{
			DSBX_QA_PersistRecord rrec = m_Records.Get(ri);
			if (rrec && rrec.m_SceneId == sceneId && rrec.m_ServerEpoch == expectEpoch)
				retainedLids.Insert(rrec.m_LogicalId);
		}
		m_LastApplyRetainedSkipped = 0;
		UpsertSceneMeta(sceneId, genN, sceneOpId);

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
			// MEN 8: guarda en cada efecto; la caducidad es error, no done parcial.
			if (!m_Probe.LeaseOk())
			{
				res.status = "error";
				res.reason = "lease_expired";
				return;
			}
			int sBase = r * scolCount;
			int nBase = r * ncolCount;

			string logicalId = args.scell.Get(sBase + idxLogical);
			bool isRetainedRow = false;
			for (int rl = 0; rl < retainedLids.Count(); rl++)
			{
				if (retainedLids.Get(rl) == logicalId)
					isRetainedRow = true;
			}
			if (isRetainedRow)
			{
				// No se crea duplicado ni registro nuevo de la fila retenida.
				m_LastApplyRetainedSkipped = m_LastApplyRetainedSkipped + 1;
				continue;
			}
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
				DSBX_QA_PersistRecord parentRec = FindRecordApplyParent(sceneId, parentId, genN);
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
			else
			{
				// Datos ausentes distinguibles de valores observados: no hay lectura de salud.
				rec.m_MaxHp = 0.0;
				rec.m_HealthHp = 0.0;
				rec.m_AliveB = 0;
				rec.m_AiAgentB = 0;
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

	protected void HandleSpawnRaw(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string tag = GetStrArg(args, "tag", "");
		string mode = GetStrArg(args, "mode", "");
		string className = GetStrArg(args, "class_name", "");
		string childCargoClass = GetStrArg(args, "child_cargo_class", "");
		string targetSceneId = GetStrArg(args, "target_scene_id", "");
		string targetParentId = GetStrArg(args, "target_parent_id", "");

		float xm = GetNumArg(args, "x_m", 0.0);
		float zm = GetNumArg(args, "z_m", 0.0);
		float yawDeg = GetNumArg(args, "yaw_deg", 0.0);
		float hRatio = GetNumArg(args, "health_mark_ratio", 1.0);

		// E1: guarda antes de crear (LeaseOk, DSBX_QA_Probe.c:447).
		// CreateObjectEx: P:/scripts/3_game/global/game.c:703; SurfaceY: game.c:1176.
		if (!m_Probe.LeaseOk())
		{
			res.status = "error";
			res.reason = "lease_expired";
			return;
		}

		Object createdObj = null;
		Object childObj = null;
		int childCountN = 0;
		bool foreignStateOk = true;
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
					if (!createdObj)
					{
						// El kit en cargo no acepta cargo (container_base.c:19-29; entityai.c:1685-1698): se llena en el suelo y se devuelve a su padre.
						EntityAI kitParentEnt = parEnt.GetHierarchyParent();
						InventoryLocation kitSrcLoc = new InventoryLocation();
						InventoryLocation kitGroundLoc = new InventoryLocation();
						InventoryLocation kitInvLoc = new InventoryLocation();
						InventoryLocation kitBackSrcLoc = new InventoryLocation();
						InventoryLocation kitBackLoc = new InventoryLocation();
						bool kitSrcOk = parEnt.GetInventory().GetCurrentInventoryLocation(kitSrcLoc);
						bool kitGroundOk = false;
						bool kitOutOk = false;
						bool kitBackFound = false;
						bool kitBackOk = false;
						if (kitParentEnt && kitSrcOk) kitGroundOk = GameInventory.SetGroundPosByOwner(kitParentEnt, parEnt, kitGroundLoc);
						if (kitGroundOk) kitOutOk = GameInventory.LocationSyncMoveEntity(kitSrcLoc, kitGroundLoc);
						if (kitOutOk && parEnt.GetInventory().FindFirstFreeLocationForNewEntity(className, FindInventoryLocationType.CARGO, kitInvLoc)) createdObj = GameInventory.LocationCreateEntity(kitInvLoc, className, FLAG_ECE_IN_INVENTORY, FLAG_RF_DEFAULT);
						if (kitOutOk && parEnt.GetInventory().GetCurrentInventoryLocation(kitBackSrcLoc) && kitParentEnt && kitParentEnt.GetInventory()) kitBackFound = kitParentEnt.GetInventory().FindFirstFreeLocationForNewEntity(parEnt.GetType(), FindInventoryLocationType.CARGO, kitBackLoc);
						if (kitBackFound) kitBackOk = GameInventory.LocationSyncMoveEntity(kitBackSrcLoc, kitBackLoc);
						foreignStateOk = kitOutOk && kitBackOk && createdObj != null;
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
				if (childCargoClass != "" && !m_Probe.LeaseOk())
				{
					res.status = "error";
					res.reason = "lease_expired";
					return;
				}
				if (childCargoClass != "")
				{
					EntityAI ctrlEnt = EntityAI.Cast(createdObj);
					// El barril nace cerrado y cerrado no recibe cargo (barrel_colorbase.c:15,512-518); abrir en servidor como actionopenbarrel.c:29-33.
					Barrel_ColorBase barrelEnt = Barrel_ColorBase.Cast(createdObj);
					if (barrelEnt && !barrelEnt.IsOpen()) barrelEnt.Open();
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

		if (mode == "persistent_control" && childCargoClass != "" && invChildren != 1)
		{
			res.status = "error";
			res.reason = "child_spawn_failed";
			return;
		}
		if (mode == "foreign_in_container" && (!foreignStateOk || obsLocKind != "cargo"))
		{
			res.status = "error";
			res.reason = "spawn_failed";
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

	protected bool AppendEntityCensusRow(string jobId, Object obj, int inRadiusB, Man director, string directorUid, array<Object> seen)
	{
		// E1 + MEN 9/14: sin lease o sin presupuesto, la captura queda fallida
		// (no un censo done truncado). LeaseOk: DSBX_QA_Probe.c:447.
		if (!m_Probe.LeaseOk())
		{
			m_CaptureFailed = true;
			m_CaptureFailReason = "lease_expired";
			m_CaptureFailJobId = jobId;
			return false;
		}
		if (m_CensusCaptureStartMs > 0.0 && m_Probe.NowMs() - m_CensusCaptureStartMs > CENSUS_CAPTURE_BUDGET_MS)
		{
			m_CaptureFailed = true;
			m_CaptureFailReason = "capture_budget_exceeded";
			m_CaptureFailJobId = jobId;
			return false;
		}
		if (!IsObjectAlive(obj))
			return true;
		for (int s = 0; s < seen.Count(); s++)
		{
			if (seen.Get(s) == obj)
				return true;
		}
		string className = obj.GetType();
		string locKind = "";
		string parentClass = "";
		string parentNetId = "";
		string slotName = "";
		string ownerUid = "";
		int invChildrenN = 0;
		ReadRealLocation(obj, director, directorUid, locKind, parentClass, parentNetId, slotName, ownerUid, invChildrenN);

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

		bool appended = m_Jobs.AppendRow(jobId, nvals, svals);
		if (appended)
			seen.Insert(obj);
		else
		{
			m_CaptureFailed = true;
			m_CaptureFailReason = "capture_truncated";
			m_CaptureFailJobId = jobId;
		}
		return appended;
	}

	protected void HandleCensusStart(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string areaTag = GetStrArg(args, "area_tag", "");
		float centerX = GetNumArg(args, "center_x_m", 0.0);
		float centerZ = GetNumArg(args, "center_z_m", 0.0);
		float radiusM = GetNumArg(args, "radius_m", 60.0);
		int includeDirectorB = (int)GetNumArg(args, "include_director_b", 0.0);

		// BLOQ 6: este arranque acredita el intento de B sobre cada censo
		// retenido; A solo se libera tras este intento o la salida acotada.
		for (int pa = 0; pa < m_PendingFinishIds.Count(); pa++)
		{
			if (m_PendingFinishIds.Get(pa) != op.op_id)
				m_PendingFinishSeen.Set(pa, 1);
		}

		string opFaultEarly = m_Probe.GetOpFault();
		ref array<ref DSBX_QA_Job> heldJobs = new array<ref DSBX_QA_Job>();
		if (opFaultEarly == "census_resource_bypass")
		{
			for (int hp = 0; hp < m_PendingFinishIds.Count(); hp++)
			{
				DSBX_QA_Job held = m_Jobs.GetJob(m_PendingFinishIds.Get(hp));
				if (held)
				{
					// Inyeccion equivalente al fake: libera el recurso solo para el chequeo de StartJob;
					// el censo A sigue vivo y se libera mas tarde, de modo que el solapamiento es real.
					held.m_Released = true;
					heldJobs.Insert(held);
				}
			}
		}
		string err = m_Jobs.StartJob(this, op.op_id, "per_census", m_CensusNcol, m_CensusScol, 5, 4096, 900000.0, "stop");
		for (int hr = 0; hr < heldJobs.Count(); hr++)
		{
			DSBX_QA_Job heldBack = heldJobs.Get(hr);
			if (heldBack)
				heldBack.m_Released = false;
		}
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
		m_CaptureFailed = false;
		m_CaptureFailReason = "";
		m_CaptureFailJobId = "";
		m_CensusCaptureStartMs = m_Probe.NowMs();
		// GetObjectsAtPosition3D: P:/scripts/3_game/global/game.c:930.
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
			if (FindRecordByObject(obj) != null)
				includeObj = true;
			else if (IsSentinelClass(cname))
				includeObj = true;
			else if (DayZCreatureAI.Cast(obj) != null)
				includeObj = true;

			if (!includeObj)
				continue;

			if (!AppendEntityCensusRow(op.op_id, obj, 1, director, directorUid, seen))
				break;
			EntityAI ent = EntityAI.Cast(obj);
			if (ent && ent.GetInventory())
			{
				array<EntityAI> subItems = new array<EntityAI>();
				ent.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, subItems);
				bool subOk = true;
				for (int sub = 0; sub < subItems.Count(); sub++)
				{
					EntityAI subEnt = subItems.Get(sub);
					if (subEnt && subEnt != ent)
					{
						if (!AppendEntityCensusRow(op.op_id, subEnt, 1, director, directorUid, seen))
						{
							subOk = false;
							break;
						}
					}
				}
				if (!subOk)
					break;
			}
		}

		for (int r = 0; r < m_Records.Count(); r++)
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
				if (!AppendEntityCensusRow(op.op_id, rec.m_RefEnt, 0, director, directorUid, seen))
					break;
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
						if (!AppendEntityCensusRow(op.op_id, dItem, 1, director, directorUid, seen))
							break;
					}
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

		float captureWallMs = m_Probe.NowMs() - m_CensusCaptureStartMs;
		PutNum(res.read, "snap_tick_ms", m_CensusCaptureStartMs);
		PutNum(res.read, "capture_wall_ms", captureWallMs);
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

	override void OnTick(float timeslice)
	{
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
		float maxHp = ent.GetMaxHealth("", "");
		if (maxHp <= 0.0)
			return false;
		float hp = ent.GetHealth("", "");
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
					if (!ent || ent.IsMan())
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
		// La base tiene que sobrevivir al reinicio de t4, y la limpieza la hacen t6 y la restauracion en frio.
	}
}
