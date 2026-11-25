class DSBX_DelPending
{
	DSBX_SceneRecord m_Rec;
	Object m_Obj;
	int m_NetLow;
	int m_NetHigh;
	int m_TicksWaited;

	void DSBX_DelPending(DSBX_SceneRecord rec, Object obj, int netLow, int netHigh)
	{
		m_Rec = rec;
		m_Obj = obj;
		m_NetLow = netLow;
		m_NetHigh = netHigh;
		m_TicksWaited = 0;
	}
}

class DSBX_SceneOps
{
	const int PHASE_IDLE = 0;
	const int PHASE_DEL_ISSUE = 1;
	const int PHASE_DEL_CONFIRM = 2;
	const int PHASE_CREATE = 3;
	const int PHASE_PUBLISH = 4;
	const int PHASE_DEL_FINISH = 5;

	const int MODE_NONE = 0;
	const int MODE_APPLY_RESET = 1;
	const int MODE_APPLY_CREATE = 2;
	const int MODE_APPLY_COMPENSATE = 3;
	const int MODE_RESET_NORMAL = 4;
	const int MODE_RESET_COMPENSATE = 5;

	DSBX_World m_World;
	DSBX_Scene m_Scene;

	int m_Phase;
	int m_Mode;
	DSBX_CacheEntry m_Entry;
	DSBX_Order m_Order;
	string m_OrderEpoch;
	string m_DocId;
	string m_Session;
	string m_OpId;
	int m_Rev;
	string m_DocHash;
	string m_PlanSha256;
	int m_TargetGenN;
	int m_RowCount;
	int m_CreateIdx;

	bool m_HadEffect;
	bool m_StopOnRetention;
	bool m_ClearGenOnFirstDelete;
	bool m_OpScopeActive;
	bool m_QueueEmptyAtStart;
	string m_TargetSess;
	string m_TargetOpId;
	string m_Parada;

	ref array<int> m_RetainedIds;
	ref array<DSBX_SceneRecord> m_DelQueue;
	ref array<int> m_DelIsChild;
	ref array<int> m_DelDepth;
	int m_DelIdx;
	ref DSBX_DelPending m_CurrentDel;
	ref array<ref DSBX_CheckpointRow> m_CheckpointRows;

	void DSBX_SceneOps(DSBX_World world, DSBX_Scene scene)
	{
		m_World = world;
		m_Scene = scene;
		m_RetainedIds = new array<int>();
		m_DelQueue = new array<DSBX_SceneRecord>();
		m_DelIsChild = new array<int>();
		m_DelDepth = new array<int>();
		m_CurrentDel = null;
		m_CheckpointRows = new array<ref DSBX_CheckpointRow>();
		ResetActive();
	}

	void ResetActive()
	{
		m_Phase = PHASE_IDLE;
		m_Mode = MODE_NONE;
		m_Entry = null;
		m_Order = null;
		m_OrderEpoch = "";
		m_DocId = "";
		m_Session = "";
		m_OpId = "";
		m_Rev = 0;
		m_DocHash = "";
		m_PlanSha256 = "";
		m_TargetGenN = 0;
		m_RowCount = 0;
		m_CreateIdx = 0;
		m_HadEffect = false;
		m_StopOnRetention = false;
		m_ClearGenOnFirstDelete = false;
		m_OpScopeActive = false;
		m_QueueEmptyAtStart = false;
		m_TargetSess = "";
		m_TargetOpId = "";
		m_Parada = "";
		m_RetainedIds.Clear();
		m_DelQueue.Clear();
		m_DelIsChild.Clear();
		m_DelDepth.Clear();
		m_DelIdx = 0;
		m_CurrentDel = null;
		m_CheckpointRows.Clear();
	}

	int EffectiveWorldSize(DSBX_Peer peer)
	{
		int wsize = 0;
		if (peer)
		{
			wsize = peer.GetWorldSize();
		}
		if (wsize <= 0 && g_Game && g_Game.GetWorld())
		{
			wsize = (int)g_Game.GetWorld().GetWorldSize();
		}
		return wsize;
	}

	bool ClassExistsInWorld(string clsName)
	{
		if (!g_Game)
		{
			return false;
		}
		if (DSBX_Wire.WireId(clsName) == "")
		{
			return false;
		}
		int scope = g_Game.ConfigGetInt("CfgVehicles " + clsName + " scope");
		return scope >= 1;
	}

	void RecordEffect()
	{
		m_HadEffect = true;
		if (m_Entry)
		{
			m_Entry.m_StepsDone = m_Entry.m_StepsDone + 1;
		}
	}

	void FinishActive(DSBX_Peer peer, string status, string reason, string readJson)
	{
		DSBX_CacheEntry doneEntry = m_Entry;
		ResetActive();
		if (peer && doneEntry)
		{
			peer.CompleteActiveEntry(doneEntry, status, reason, readJson);
		}
	}

	string CurrentReadJson(string docId, string obsJson)
	{
		if (!m_World || !m_Scene || docId == "")
		{
			return "{}";
		}
		return DSBX_SceneWire.SceneReadJson(m_World.GetEpoch(), m_Scene, docId, obsJson);
	}

	bool IsGoneByNetId(int netLow, int netHigh)
	{
		if (netLow == 0 && netHigh == 0)
		{
			return false;
		}
		if (!g_Game)
		{
			return false;
		}
		return g_Game.GetObjectByNetworkId(netLow, netHigh) == null;
	}

	// DP-6 y §5.4: registra las tres senales por tick para F2P-10.
	void LogDeleteSignal(DSBX_Peer peer, string lid, int netLow, int netHigh, Object obj, int confirmedB, int failedB)
	{
		if (!peer)
		{
			return;
		}
		int tickMs = peer.TickMs();
		int frame = peer.GetTickFrame();
		int sigRef = 0;
		if (!obj)
		{
			sigRef = 1;
		}
		int sigPend = 0;
		if (DSBX_Scene.IsMarkedForDeletion(obj))
		{
			sigPend = 1;
		}
		int sigNet = 0;
		if (IsGoneByNetId(netLow, netHigh))
		{
			sigNet = 1;
		}
		int confirmTickMs = 0;
		if (confirmedB == 1 || failedB == 1)
		{
			confirmTickMs = tickMs;
		}
		string msg = "DSBX_SCENE_DEL tick_ms=" + tickMs.ToString() + " frame=" + frame.ToString();
		msg = msg + " lid=" + lid + " net_low=" + netLow.ToString() + " net_high=" + netHigh.ToString();
		msg = msg + " signal_ref_b=" + sigRef.ToString() + " signal_pending_b=" + sigPend.ToString();
		msg = msg + " signal_by_netid_b=" + sigNet.ToString() + " deleted_confirmed_b=" + confirmedB.ToString();
		msg = msg + " delete_failed_b=" + failedB.ToString() + " confirm_tick_ms=" + confirmTickMs.ToString();
		peer.Log(msg);
	}

	void StartOrder(DSBX_Peer peer, DSBX_CacheEntry entry)
	{
		if (!peer || !entry || !entry.m_Order || !m_World || !m_Scene)
		{
			if (peer && entry)
			{
				peer.FinishEntry(entry, "rejected", "bad_args", "{}");
			}
			return;
		}
		string verb = entry.m_Order.verb;
		if (verb == "scene.observe")
		{
			ExecuteObserve(peer, entry);
			return;
		}
		if (verb == "scene.apply")
		{
			StartApply(peer, entry);
			return;
		}
		if (verb == "scene.reset")
		{
			StartReset(peer, entry);
			return;
		}
		peer.FinishEntry(entry, "rejected", "unknown_verb", "{}");
	}

	// --- scene.observe (§3.4, §3.5, M15, DP-8) ---

	void ExecuteObserve(DSBX_Peer peer, DSBX_CacheEntry entry)
	{
		DSBX_Order order = entry.m_Order;
		string worldEpoch = m_World.GetEpoch();
		if (order.epoch != worldEpoch)
		{
			peer.FinishEntry(entry, "rejected", "stale_epoch", "{}");
			return;
		}
		DSBX_Args args = order.args;
		if (!args || !DSBX_SceneWire.ValidDocId(args.doc_id))
		{
			peer.FinishEntry(entry, "rejected", "bad_args", "{}");
			return;
		}
		if (args.at != "checkpoint" && args.at != "now")
		{
			peer.FinishEntry(entry, "rejected", "bad_args", "{}");
			return;
		}
		string docId = args.doc_id;
		string obsJson = "";
		if (args.at == "checkpoint")
		{
			DSBX_SceneState st = m_Scene.GetSceneState(docId, false);
			if (st && st.m_Generation)
			{
				obsJson = DSBX_SceneWire.ObsCheckpointJson(st.m_Checkpoint);
			}
			else
			{
				obsJson = "{\"at\":\"checkpoint\",\"rows\":[]}";
			}
		}
		else
		{
			obsJson = BuildObserveNowJson(peer, worldEpoch, docId);
		}
		if (obsJson == "")
		{
			peer.FinishEntry(entry, "rejected", "bad_args", "{}");
			return;
		}
		string readJson = DSBX_SceneWire.SceneReadJson(worldEpoch, m_Scene, docId, obsJson);
		int cap = peer.GetWireCap();
		if (cap <= 0 || cap > DSBX_WIRE_CAP)
		{
			cap = DSBX_WIRE_CAP;
		}
		string testBody = DSBX_Wire.ResultBody(order.op_id, order.session, order.epoch, "done", "", false, readJson);
		if (testBody == "" || testBody.Length() > cap)
		{
			peer.FinishEntry(entry, "rejected", "result_too_large", "{}");
			return;
		}
		peer.FinishEntry(entry, "done", "", readJson);
	}

	string BuildObserveNowJson(DSBX_Peer peer, string epoch, string docId)
	{
		array<DSBX_SceneRecord> sceneRecs = new array<DSBX_SceneRecord>();
		m_Scene.GetSceneRecords(epoch, docId, sceneRecs);
		array<Object> sceneObjs = new array<Object>();
		int s = 0;
		while (s < sceneRecs.Count())
		{
			DSBX_SceneRecord sr = sceneRecs.Get(s);
			if (sr)
			{
				Object sObj = sr.ResolveLiveObject();
				if (sObj && !DSBX_Scene.IsMarkedForDeletion(sObj))
				{
					sceneObjs.Insert(sObj);
				}
			}
			s = s + 1;
		}
		int limitMm = DSBX_SceneWire.WorldLimitMm(EffectiveWorldSize(peer));
		array<string> rowJsons = new array<string>();
		int i = 0;
		while (i < sceneRecs.Count())
		{
			DSBX_SceneRecord rec = sceneRecs.Get(i);
			if (rec && rec.m_ParentLid == "")
			{
				Object obj = rec.ResolveLiveObject();
				bool alive = (obj != null) && !DSBX_Scene.IsMarkedForDeletion(obj) && obj.IsAlive();
				if (!alive)
				{
					rowJsons.Insert(DSBX_SceneWire.NowRowDeadJson(rec.m_Lid));
				}
				else
				{
					vector pos = obj.GetPosition();
					vector ori = obj.GetOrientation();
					int xMm = 0;
					int yMm = 0;
					int zMm = 0;
					int yawMdeg = 0;
					bool okX = DSBX_SceneWire.MetersToMmChecked(pos[0], 0, limitMm, xMm);
					bool okY = DSBX_SceneWire.MetersToMmChecked(pos[1], -DSBX_SceneConst.MAX_Y_MM, DSBX_SceneConst.MAX_Y_MM, yMm);
					bool okZ = DSBX_SceneWire.MetersToMmChecked(pos[2], 0, limitMm, zMm);
					bool okYaw = DSBX_SceneWire.YawDegToMdegChecked(ori[0], yawMdeg);
					if (!okX || !okY || !okZ || !okYaw)
					{
						rowJsons.Insert(DSBX_SceneWire.NowRowDeadJson(rec.m_Lid));
					}
					else
					{
						int hpMilli = DSBX_SceneConst.MAX_HP_MILLI;
						EntityAI ent = EntityAI.Cast(obj);
						if (ent && ent.HasDamageSystem())
						{
							float maxHp = ent.GetMaxHealth("", "");
							if (maxHp > 0.0)
							{
								hpMilli = DSBX_SceneWire.RatioToMilli(ent.GetHealth("", "") / maxHp);
							}
						}
						int nOwn = 0;
						int nForeign = 0;
						if (ent && ent.GetInventory())
						{
							array<EntityAI> items = new array<EntityAI>();
							ent.GetInventory().EnumerateInventory(InventoryTraversalType.PREORDER, items);
							int k = 0;
							while (k < items.Count())
							{
								EntityAI child = items.Get(k);
								if (child && child != ent && !DSBX_Scene.IsMarkedForDeletion(child))
								{
									if (DSBX_Scene.ContainsObject(sceneObjs, child))
									{
										nOwn = nOwn + 1;
									}
									else
									{
										nForeign = nForeign + 1;
									}
								}
								k = k + 1;
							}
						}
						rowJsons.Insert(DSBX_SceneWire.NowRowAliveJson(rec.m_Lid, xMm, yMm, zMm, yawMdeg, hpMilli, nOwn, nForeign));
					}
				}
			}
			i = i + 1;
		}
		return DSBX_SceneWire.ObsNowJson(rowJsons);
	}

	// --- scene.apply validacion sin efecto (etapas 1, 2 y 3) ---

	string ValidatePlan(DSBX_Peer peer, DSBX_Args args, out string outDocId)
	{
		outDocId = "";
		if (!args)
		{
			return "bad_plan";
		}
		if (!DSBX_SceneWire.ValidDocId(args.doc_id))
		{
			return "bad_plan";
		}
		outDocId = args.doc_id;
		if (args.rev < 0 || args.rev > DSBX_SceneConst.MAX_REV)
		{
			return "bad_plan";
		}
		if (!DSBX_Messages.IsHex(args.hash, 64) || !DSBX_Messages.IsHex(args.plan_sha256, 64))
		{
			return "bad_plan";
		}
		if (!args.classes)
		{
			return "bad_plan";
		}
		int nClasses = args.classes.Count();
		int cIdx = 0;
		while (cIdx < nClasses)
		{
			string cls = args.classes.Get(cIdx);
			if (!DSBX_SceneWire.IsAsciiNonEmpty(cls))
			{
				return "bad_plan";
			}
			if (cIdx > 0 && DSBX_Scene.CompareAscii(args.classes.Get(cIdx - 1), cls) >= 0)
			{
				return "bad_plan";
			}
			cIdx = cIdx + 1;
		}
		if (!args.lid || !args.ci || !args.x_mm || !args.z_mm || !args.yaw_mdeg)
		{
			return "bad_plan";
		}
		int nRows = args.lid.Count();
		if (args.ci.Count() != nRows || args.x_mm.Count() != nRows || args.z_mm.Count() != nRows || args.yaw_mdeg.Count() != nRows)
		{
			return "bad_plan";
		}

		ref map<string, bool> seenLids = new map<string, bool>();
		array<int> usedCi = new array<int>();
		int u = 0;
		while (u < nClasses)
		{
			usedCi.Insert(0);
			u = u + 1;
		}
		int cntObj = 0;
		int cntZmb = 0;
		int cntAni = 0;

		int r = 0;
		while (r < nRows)
		{
			string lid = args.lid.Get(r);
			if (!DSBX_SceneWire.ValidLid(lid) || seenLids.Contains(lid))
			{
				return "bad_plan";
			}
			seenLids.Set(lid, true);
			int ci = args.ci.Get(r);
			if (ci < 0 || ci >= nClasses)
			{
				return "bad_plan";
			}
			int yawMdeg = args.yaw_mdeg.Get(r);
			if (yawMdeg < 0 || yawMdeg >= DSBX_SceneConst.YAW_MDEG_MOD)
			{
				return "bad_plan";
			}
			int kind = DSBX_SceneWire.LidKind(lid);
			if (kind == 0)
			{
				cntObj = cntObj + 1;
			}
			else if (kind == 1)
			{
				cntZmb = cntZmb + 1;
			}
			else if (kind == 2)
			{
				cntAni = cntAni + 1;
			}
			else
			{
				return "bad_plan";
			}
			usedCi.Set(ci, 1);
			r = r + 1;
		}

		// M14: todas las clases de `classes` tienen que usarse (tambien con 0 filas:
		// un plan v1.2.2 con `rows` y sin columnas llega con 0 filas y `classes` no vacio -> bad_plan).
		int uc = 0;
		while (uc < nClasses)
		{
			if (usedCi.Get(uc) == 0)
			{
				return "bad_plan";
			}
			uc = uc + 1;
		}

		// A6: falla cerrado sin caps validos.
		if (!args.caps)
		{
			return "budget_exceeded";
		}
		if (args.caps.objeto < 0 || args.caps.infectado < 0 || args.caps.animal < 0 || args.caps.total < -1)
		{
			return "budget_exceeded";
		}

		// Etapa 1b: cada clase existe en el mundo.
		int k = 0;
		while (k < nClasses)
		{
			if (!ClassExistsInWorld(args.classes.Get(k)))
			{
				return "unknown_class";
			}
			k = k + 1;
		}

		// Etapa 1c: coordenadas en [0, world_size * 1000] mm.
		int limitMm = DSBX_SceneWire.WorldLimitMm(EffectiveWorldSize(peer));
		int m = 0;
		while (m < nRows)
		{
			int xm = args.x_mm.Get(m);
			int zm = args.z_mm.Get(m);
			if (xm < 0 || xm > limitMm || zm < 0 || zm > limitMm)
			{
				return "out_of_map";
			}
			m = m + 1;
		}

		// Etapa 2: reservar presupuesto (total == -1 es sin tope total, DP-2).
		if (cntObj > args.caps.objeto || cntZmb > args.caps.infectado || cntAni > args.caps.animal)
		{
			return "budget_exceeded";
		}
		if (args.caps.total >= 0 && nRows > args.caps.total)
		{
			return "budget_exceeded";
		}
		return "";
	}

	void StartApply(DSBX_Peer peer, DSBX_CacheEntry entry)
	{
		DSBX_Order order = entry.m_Order;
		string worldEpoch = m_World.GetEpoch();
		if (order.epoch != worldEpoch)
		{
			peer.FinishEntry(entry, "rejected", "stale_epoch", "{}");
			return;
		}
		string docId = "";
		string valErr = ValidatePlan(peer, order.args, docId);
		if (valErr != "")
		{
			string errRead = "{}";
			if (docId != "")
			{
				errRead = CurrentReadJson(docId, "");
			}
			peer.FinishEntry(entry, "rejected", valErr, errRead);
			return;
		}

		// Etapa 3: retencion previa sin efecto (D5, D7).
		array<DSBX_SceneRecord> deletable = new array<DSBX_SceneRecord>();
		m_Scene.GetSceneRecords(worldEpoch, docId, deletable);
		array<int> initialRetained = new array<int>();
		DSBX_Scene.ComputeRetention(deletable, initialRetained);
		if (initialRetained.Count() > 0)
		{
			peer.FinishEntry(entry, "rejected", "foreign_content_retained", CurrentReadJson(docId, ""));
			return;
		}

		ResetActive();
		m_Entry = entry;
		m_Order = order;
		m_OrderEpoch = order.epoch;
		m_DocId = docId;
		m_Session = order.session;
		m_OpId = order.op_id;
		m_Rev = order.args.rev;
		m_DocHash = order.args.hash;
		m_PlanSha256 = order.args.plan_sha256;
		m_RowCount = order.args.lid.Count();

		m_Mode = MODE_APPLY_RESET;
		m_StopOnRetention = true;
		m_ClearGenOnFirstDelete = true;
		m_OpScopeActive = false;
		DSBX_Scene.BuildDeletionQueue(deletable, m_RetainedIds, m_DelQueue, m_DelIsChild, m_DelDepth);
		m_QueueEmptyAtStart = (m_DelQueue.Count() == 0);
		if (m_QueueEmptyAtStart)
		{
			m_Phase = PHASE_DEL_FINISH;
		}
		else
		{
			m_Phase = PHASE_DEL_ISSUE;
		}
		peer.ActivateEntry(entry);
	}

	// --- scene.reset validacion sin efecto (§3.3, §3.4, M13) ---

	void StartReset(DSBX_Peer peer, DSBX_CacheEntry entry)
	{
		DSBX_Order order = entry.m_Order;
		string worldEpoch = m_World.GetEpoch();
		if (order.epoch != worldEpoch)
		{
			peer.FinishEntry(entry, "rejected", "stale_epoch", "{}");
			return;
		}
		DSBX_Args args = order.args;
		if (!args || !DSBX_SceneWire.ValidDocId(args.doc_id))
		{
			peer.FinishEntry(entry, "rejected", "bad_args", "{}");
			return;
		}
		string docId = args.doc_id;

		bool hasIfPending = false;
		string targetSess = "";
		string targetOp = "";
		if (args.if_pending)
		{
			string ipSess = args.if_pending.session;
			string ipOp = args.if_pending.op_id;
			if (ipSess == "" && ipOp == "")
			{
				hasIfPending = false;
			}
			else if (ipSess == "" || ipOp == "")
			{
				peer.FinishEntry(entry, "rejected", "bad_args", CurrentReadJson(docId, ""));
				return;
			}
			else
			{
				hasIfPending = true;
				targetSess = ipSess;
				targetOp = ipOp;
			}
		}

		array<DSBX_SceneRecord> deletable = new array<DSBX_SceneRecord>();
		if (hasIfPending)
		{
			DSBX_SceneState stCur = m_Scene.GetSceneState(docId, false);
			int curPendN = m_Scene.CountOpRecords(worldEpoch, docId, targetSess, targetOp);
			if (!stCur || !stCur.HasPendingOrder(targetSess, targetOp) || curPendN == 0)
			{
				peer.FinishEntry(entry, "rejected", "not_pending", CurrentReadJson(docId, ""));
				return;
			}
			m_Scene.GetOpRecords(worldEpoch, docId, targetSess, targetOp, deletable);
		}
		else
		{
			m_Scene.GetSceneRecords(worldEpoch, docId, deletable);
		}

		ResetActive();
		m_Entry = entry;
		m_Order = order;
		m_OrderEpoch = order.epoch;
		m_DocId = docId;
		m_Session = order.session;
		m_OpId = order.op_id;

		DSBX_Scene.ComputeRetention(deletable, m_RetainedIds);
		DSBX_Scene.BuildDeletionQueue(deletable, m_RetainedIds, m_DelQueue, m_DelIsChild, m_DelDepth);
		m_QueueEmptyAtStart = (m_DelQueue.Count() == 0);
		m_StopOnRetention = false;
		if (hasIfPending)
		{
			m_Mode = MODE_RESET_COMPENSATE;
			m_ClearGenOnFirstDelete = false;
			m_OpScopeActive = true;
			m_TargetSess = targetSess;
			m_TargetOpId = targetOp;
		}
		else
		{
			m_Mode = MODE_RESET_NORMAL;
			m_ClearGenOnFirstDelete = true;
			m_OpScopeActive = false;
		}
		if (m_QueueEmptyAtStart)
		{
			m_Phase = PHASE_DEL_FINISH;
		}
		else
		{
			m_Phase = PHASE_DEL_ISSUE;
		}
		peer.ActivateEntry(entry);
	}

	// --- Maquina por lotes: un paso por tick desde AdvanceExecution ---

	void AdvanceTick(DSBX_Peer peer)
	{
		if (m_Phase == PHASE_IDLE || !peer || !m_Order || !m_World || !m_Scene)
		{
			return;
		}
		if (m_Phase == PHASE_DEL_ISSUE)
		{
			StepDeleteIssue(peer);
			return;
		}
		if (m_Phase == PHASE_DEL_CONFIRM)
		{
			StepDeleteConfirm(peer);
			return;
		}
		if (m_Phase == PHASE_DEL_FINISH)
		{
			FinishDeletePhase(peer);
			return;
		}
		if (m_Phase == PHASE_CREATE)
		{
			StepCreate(peer);
			return;
		}
		if (m_Phase == PHASE_PUBLISH)
		{
			StepPublish(peer);
		}
	}

	void GetCurrentScopeRecords(string epoch, array<DSBX_SceneRecord> outRecs)
	{
		if (m_OpScopeActive)
		{
			m_Scene.GetOpRecords(epoch, m_DocId, m_TargetSess, m_TargetOpId, outRecs);
		}
		else
		{
			m_Scene.GetSceneRecords(epoch, m_DocId, outRecs);
		}
	}

	void StepDeleteIssue(DSBX_Peer peer)
	{
		array<DSBX_SceneRecord> scopeRecs = new array<DSBX_SceneRecord>();
		array<Object> delObjs = new array<Object>();
		array<DSBX_SceneRecord> delObjRecs = new array<DSBX_SceneRecord>();

		while (m_DelIdx < m_DelQueue.Count())
		{
			// M3: antes de cada efecto, comprobar epoch.
			if (m_World.GetEpoch() != m_OrderEpoch)
			{
				m_Parada = "stale_epoch";
				break;
			}

			DSBX_SceneRecord rec = m_DelQueue.Get(m_DelIdx);
			m_DelIdx = m_DelIdx + 1;
			if (!rec || DSBX_Scene.ContainsInt(m_RetainedIds, rec.m_RecId) || !m_Scene.HasRecord(rec))
			{
				continue;
			}

			// Lease, plazo, sesion y conn antes de cada efecto (DSBX_Peer.EffectGuard).
			if (!peer.EffectGuard(m_Order))
			{
				m_Parada = peer.GetGuardFailReason();
				break;
			}

			if (m_World.GetEpoch() != m_OrderEpoch)
			{
				m_Parada = "stale_epoch";
				break;
			}

			Object obj = rec.ResolveLiveObject();
			if (!obj)
			{
				// DP-6: sin net_id valido no se puede confirmar el borrado por GetObjectByNetworkId.
				if (rec.m_NetLow == 0 && rec.m_NetHigh == 0)
				{
					LogDeleteSignal(peer, rec.m_Lid, 0, 0, null, 0, 1);
					m_Parada = "delete_failed";
					break;
				}
				m_Scene.RemoveRecord(rec);
				RecordEffect();
				if (m_ClearGenOnFirstDelete)
				{
					DSBX_SceneState stGone = m_Scene.GetSceneState(m_DocId, true);
					stGone.ClearGeneration();
				}
				continue;
			}

			// D5/TOCTOU y P-02: recalcular conjunto borrable y retencion justo antes de cada borrado.
			GetCurrentScopeRecords(m_OrderEpoch, scopeRecs);
			DSBX_Scene.BuildLiveDeletable(scopeRecs, delObjs, delObjRecs);
			if (DSBX_Scene.HasForeignDescendant(obj, delObjs))
			{
				DSBX_Scene.MarkRetainedWithAncestors(obj, rec, delObjs, delObjRecs, m_RetainedIds);
				if (m_StopOnRetention)
				{
					m_Parada = "retention_stop";
					break;
				}
				continue;
			}

			// DP-6: si net_id sigue siendo 0:0 tras RefreshNetworkId, no se da por confirmado -> delete_failed.
			rec.RefreshNetworkId(obj);
			int netLow = rec.m_NetLow;
			int netHigh = rec.m_NetHigh;
			if (netLow == 0 && netHigh == 0)
			{
				LogDeleteSignal(peer, rec.m_Lid, netLow, netHigh, obj, 0, 1);
				m_Parada = "delete_failed";
				break;
			}

			// DP-6 y §3.4 paso 3: emitir un solo Delete() y confirmar antes de emitir el siguiente.
			obj.Delete();
			LogDeleteSignal(peer, rec.m_Lid, netLow, netHigh, obj, 0, 0);
			m_CurrentDel = new DSBX_DelPending(rec, obj, netLow, netHigh);
			m_Phase = PHASE_DEL_CONFIRM;
			return;
		}

		m_Phase = PHASE_DEL_FINISH;
		FinishDeletePhase(peer);
	}

	void StepDeleteConfirm(DSBX_Peer peer)
	{
		if (m_World.GetEpoch() != m_OrderEpoch)
		{
			m_CurrentDel = null;
			m_Parada = "stale_epoch";
			m_Phase = PHASE_DEL_FINISH;
			FinishDeletePhase(peer);
			return;
		}
		if (!m_CurrentDel)
		{
			m_Phase = PHASE_DEL_FINISH;
			FinishDeletePhase(peer);
			return;
		}

		m_CurrentDel.m_TicksWaited = m_CurrentDel.m_TicksWaited + 1;
		if (IsGoneByNetId(m_CurrentDel.m_NetLow, m_CurrentDel.m_NetHigh))
		{
			LogDeleteSignal(peer, m_CurrentDel.m_Rec.m_Lid, m_CurrentDel.m_NetLow, m_CurrentDel.m_NetHigh, m_CurrentDel.m_Obj, 1, 0);
			m_Scene.RemoveRecord(m_CurrentDel.m_Rec);
			RecordEffect();
			if (m_ClearGenOnFirstDelete)
			{
				DSBX_SceneState stDel = m_Scene.GetSceneState(m_DocId, true);
				stDel.ClearGeneration();
			}
			m_CurrentDel = null;
			if (m_DelIdx >= m_DelQueue.Count())
			{
				m_Phase = PHASE_DEL_FINISH;
				FinishDeletePhase(peer);
				return;
			}
			m_Phase = PHASE_DEL_ISSUE;
			StepDeleteIssue(peer);
			return;
		}

		if (m_CurrentDel.m_TicksWaited >= DSBX_SceneConst.DEL_CONFIRM_TICKS)
		{
			LogDeleteSignal(peer, m_CurrentDel.m_Rec.m_Lid, m_CurrentDel.m_NetLow, m_CurrentDel.m_NetHigh, m_CurrentDel.m_Obj, 0, 1);
			m_CurrentDel = null;
			m_Parada = "delete_failed";
			m_Phase = PHASE_DEL_FINISH;
			FinishDeletePhase(peer);
			return;
		}

		LogDeleteSignal(peer, m_CurrentDel.m_Rec.m_Lid, m_CurrentDel.m_NetLow, m_CurrentDel.m_NetHigh, m_CurrentDel.m_Obj, 0, 0);
	}

	void CollectRetainedRecords(array<DSBX_SceneRecord> sourceRecs, array<DSBX_SceneRecord> outRetained)
	{
		outRetained.Clear();
		int i = 0;
		while (i < sourceRecs.Count())
		{
			DSBX_SceneRecord r = sourceRecs.Get(i);
			if (r && DSBX_Scene.ContainsInt(m_RetainedIds, r.m_RecId))
			{
				outRetained.Insert(r);
			}
			i = i + 1;
		}
	}

	void FinishDeletePhase(DSBX_Peer peer)
	{
		// M3: antes de escribir estado (last, retained, pending), si el epoch cambio, parar sin escribir.
		if (m_World.GetEpoch() != m_OrderEpoch)
		{
			string stEpoch = "rejected";
			if (m_HadEffect)
			{
				stEpoch = "error";
			}
			FinishActive(peer, stEpoch, "stale_epoch", CurrentReadJson(m_DocId, ""));
			return;
		}

		if (m_Mode == MODE_APPLY_RESET)
		{
			FinishApplyReset(peer);
			return;
		}
		if (m_Mode == MODE_APPLY_COMPENSATE)
		{
			FinishApplyCompensation(peer);
			return;
		}
		FinishResetOp(peer);
	}

	void FinishApplyReset(DSBX_Peer peer)
	{
		array<DSBX_SceneRecord> sceneNow = new array<DSBX_SceneRecord>();
		m_Scene.GetSceneRecords(m_OrderEpoch, m_DocId, sceneNow);
		array<DSBX_SceneRecord> retainedRecs = new array<DSBX_SceneRecord>();
		CollectRetainedRecords(sceneNow, retainedRecs);

		if (m_Parada == "stale_epoch")
		{
			string stEp = "rejected";
			if (m_HadEffect)
			{
				stEp = "error";
			}
			FinishActive(peer, stEp, "stale_epoch", CurrentReadJson(m_DocId, ""));
			return;
		}
		if (m_Parada == "delete_failed")
		{
			if (!m_HadEffect)
			{
				FinishActive(peer, "rejected", "delete_failed", CurrentReadJson(m_DocId, ""));
				return;
			}
			DSBX_SceneState stDf = m_Scene.GetSceneState(m_DocId, true);
			m_Scene.SetRetention(stDf, retainedRecs);
			m_Scene.PrunePending(m_OrderEpoch, m_DocId);
			stDf.SetLast(m_Session, m_OpId, "scene.apply", "interrupted");
			FinishActive(peer, "error", "delete_failed", CurrentReadJson(m_DocId, ""));
			return;
		}
		if (m_Parada != "" && m_Parada != "retention_stop")
		{
			if (!m_HadEffect)
			{
				FinishActive(peer, "rejected", m_Parada, CurrentReadJson(m_DocId, ""));
				return;
			}
			DSBX_SceneState stInt = m_Scene.GetSceneState(m_DocId, true);
			m_Scene.SetRetention(stInt, retainedRecs);
			m_Scene.PrunePending(m_OrderEpoch, m_DocId);
			stInt.SetLast(m_Session, m_OpId, "scene.apply", "interrupted");
			FinishActive(peer, "error", m_Parada, CurrentReadJson(m_DocId, ""));
			return;
		}
		if (m_Parada == "retention_stop")
		{
			if (!m_HadEffect)
			{
				FinishActive(peer, "rejected", "foreign_content_retained", CurrentReadJson(m_DocId, ""));
				return;
			}
			DSBX_SceneState stRet = m_Scene.GetSceneState(m_DocId, true);
			m_Scene.SetRetention(stRet, retainedRecs);
			m_Scene.PrunePending(m_OrderEpoch, m_DocId);
			stRet.SetLast(m_Session, m_OpId, "scene.apply", "retained");
			FinishActive(peer, "error", "foreign_content_retained", CurrentReadJson(m_DocId, ""));
			return;
		}

		// M9: releer lo borrable antes de crear; nunca crear si la escena no quedo vacia (D7).
		array<DSBX_SceneRecord> leftovers = new array<DSBX_SceneRecord>();
		m_Scene.GetSceneRecords(m_OrderEpoch, m_DocId, leftovers);
		if (leftovers.Count() > 0)
		{
			if (!m_HadEffect)
			{
				FinishActive(peer, "rejected", "foreign_content_retained", CurrentReadJson(m_DocId, ""));
				return;
			}
			DSBX_SceneState stLeft = m_Scene.GetSceneState(m_DocId, true);
			m_Scene.SetRetention(stLeft, leftovers);
			m_Scene.PrunePending(m_OrderEpoch, m_DocId);
			stLeft.SetLast(m_Session, m_OpId, "scene.apply", "retained");
			FinishActive(peer, "error", "foreign_content_retained", CurrentReadJson(m_DocId, ""));
			return;
		}

		DSBX_SceneState stNext = m_Scene.GetSceneState(m_DocId, true);
		m_TargetGenN = stNext.m_GenN + 1;
		m_Mode = MODE_APPLY_CREATE;
		m_CreateIdx = 0;
		m_CheckpointRows.Clear();

		if (m_RowCount == 0)
		{
			if (!m_HadEffect)
			{
				if (!peer.EffectGuard(m_Order))
				{
					if (m_World.GetEpoch() != m_OrderEpoch)
					{
						FinishActive(peer, "rejected", "stale_epoch", CurrentReadJson(m_DocId, ""));
						return;
					}
					string guardReason = peer.GetGuardFailReason();
					string guardRead = CurrentReadJson(m_DocId, "");
					FinishActive(peer, "rejected", guardReason, guardRead);
					return;
				}
			}
			m_Phase = PHASE_PUBLISH;
			StepPublish(peer);
			return;
		}

		m_Phase = PHASE_CREATE;
		if (m_QueueEmptyAtStart)
		{
			StepCreate(peer);
		}
	}

	void FinishApplyCompensation(DSBX_Peer peer)
	{
		if (m_Parada == "stale_epoch")
		{
			FinishActive(peer, "error", "stale_epoch", CurrentReadJson(m_DocId, ""));
			return;
		}
		DSBX_SceneState st = m_Scene.GetSceneState(m_DocId, true);
		array<DSBX_SceneRecord> remOp = new array<DSBX_SceneRecord>();
		m_Scene.GetOpRecords(m_OrderEpoch, m_DocId, m_Session, m_OpId, remOp);
		array<DSBX_SceneRecord> retainedRecs = new array<DSBX_SceneRecord>();
		CollectRetainedRecords(remOp, retainedRecs);
		m_Scene.SetRetention(st, retainedRecs);
		m_Scene.PrunePending(m_OrderEpoch, m_DocId);

		if (m_Parada != "")
		{
			st.SetLast(m_Session, m_OpId, "scene.apply", "interrupted");
			// M7: la compensacion dentro de la orden mantiene create_failed.
			FinishActive(peer, "error", "create_failed", CurrentReadJson(m_DocId, ""));
			return;
		}
		string outcome = "compensated";
		if (retainedRecs.Count() > 0)
		{
			outcome = "retained";
		}
		st.SetLast(m_Session, m_OpId, "scene.apply", outcome);
		FinishActive(peer, "error", "create_failed", CurrentReadJson(m_DocId, ""));
	}

	void FinishResetOp(DSBX_Peer peer)
	{
		if (m_QueueEmptyAtStart && m_Parada == "")
		{
			if (!peer.EffectGuard(m_Order))
			{
				if (m_World.GetEpoch() != m_OrderEpoch)
				{
					FinishActive(peer, "rejected", "stale_epoch", CurrentReadJson(m_DocId, ""));
					return;
				}
				string guardReason = peer.GetGuardFailReason();
				string guardRead = CurrentReadJson(m_DocId, "");
				FinishActive(peer, "rejected", guardReason, guardRead);
				return;
			}
			if (m_World.GetEpoch() != m_OrderEpoch)
			{
				FinishActive(peer, "rejected", "stale_epoch", CurrentReadJson(m_DocId, ""));
				return;
			}
		}

		array<DSBX_SceneRecord> sceneNow = new array<DSBX_SceneRecord>();
		m_Scene.GetSceneRecords(m_OrderEpoch, m_DocId, sceneNow);
		array<DSBX_SceneRecord> retainedRecs = new array<DSBX_SceneRecord>();
		CollectRetainedRecords(sceneNow, retainedRecs);

		if (m_Parada == "stale_epoch")
		{
			string stEp = "rejected";
			if (m_HadEffect)
			{
				stEp = "error";
			}
			FinishActive(peer, stEp, "stale_epoch", CurrentReadJson(m_DocId, ""));
			return;
		}
		if (m_Parada != "")
		{
			if (!m_HadEffect)
			{
				FinishActive(peer, "rejected", m_Parada, CurrentReadJson(m_DocId, ""));
				return;
			}
			DSBX_SceneState stErr = m_Scene.GetSceneState(m_DocId, true);
			m_Scene.SetRetention(stErr, retainedRecs);
			m_Scene.PrunePending(m_OrderEpoch, m_DocId);
			if (m_Mode == MODE_RESET_COMPENSATE)
			{
				// M5: una compensacion if_pending interrumpida deja last del apply.
				stErr.SetLast(m_TargetSess, m_TargetOpId, "scene.apply", "interrupted");
			}
			else
			{
				stErr.SetLast(m_Session, m_OpId, "scene.reset", "interrupted");
			}
			FinishActive(peer, "error", m_Parada, CurrentReadJson(m_DocId, ""));
			return;
		}

		DSBX_SceneState stDone = m_Scene.GetSceneState(m_DocId, true);
		m_Scene.SetRetention(stDone, retainedRecs);
		if (m_Mode == MODE_RESET_NORMAL)
		{
			stDone.ClearGeneration();
			stDone.m_PendingOrders.Clear();
			string outReset = "done";
			if (retainedRecs.Count() > 0)
			{
				outReset = "retained";
			}
			stDone.SetLast(m_Session, m_OpId, "scene.reset", outReset);
		}
		else
		{
			m_Scene.PrunePending(m_OrderEpoch, m_DocId);
			string outComp = "compensated";
			if (retainedRecs.Count() > 0)
			{
				outComp = "retained";
			}
			stDone.SetLast(m_TargetSess, m_TargetOpId, "scene.apply", outComp);
		}
		FinishActive(peer, "done", "", CurrentReadJson(m_DocId, ""));
	}

	// --- Etapa 5: crear por lotes de SCENE_BATCH por tick (§4.3) ---

	int FindClassIndex(array<string> classes, string clsName)
	{
		if (!classes)
		{
			return -1;
		}
		int i = 0;
		while (i < classes.Count())
		{
			if (classes.Get(i) == clsName)
			{
				return i;
			}
			i = i + 1;
		}
		return -1;
	}

	void StartInOrderCompensation(DSBX_Peer peer, int effectsThisTick)
	{
		array<DSBX_SceneRecord> opRecs = new array<DSBX_SceneRecord>();
		m_Scene.GetOpRecords(m_OrderEpoch, m_DocId, m_Session, m_OpId, opRecs);
		// M12: creacion fallida antes de ningun efecto -> rejected/create_failed sin tocar last.
		if (opRecs.Count() == 0 && !m_HadEffect)
		{
			FinishActive(peer, "rejected", "create_failed", CurrentReadJson(m_DocId, ""));
			return;
		}

		m_Mode = MODE_APPLY_COMPENSATE;
		m_StopOnRetention = false;
		m_ClearGenOnFirstDelete = false;
		m_OpScopeActive = true;
		m_TargetSess = m_Session;
		m_TargetOpId = m_OpId;
		m_Parada = "";
		m_CurrentDel = null;
		m_DelIdx = 0;

		DSBX_Scene.ComputeRetention(opRecs, m_RetainedIds);
		DSBX_Scene.BuildDeletionQueue(opRecs, m_RetainedIds, m_DelQueue, m_DelIsChild, m_DelDepth);
		m_QueueEmptyAtStart = (m_DelQueue.Count() == 0);
		if (m_QueueEmptyAtStart)
		{
			m_Phase = PHASE_DEL_FINISH;
			if (effectsThisTick == 0)
			{
				FinishDeletePhase(peer);
			}
			return;
		}
		// M10: respetar SCENE_BATCH dejando la compensacion al tick siguiente si ya hubo efectos.
		m_Phase = PHASE_DEL_ISSUE;
		if (effectsThisTick == 0)
		{
			StepDeleteIssue(peer);
		}
	}

	void StepCreate(DSBX_Peer peer)
	{
		DSBX_Args args = m_Order.args;
		int limitMm = DSBX_SceneWire.WorldLimitMm(EffectiveWorldSize(peer));
		int inBatch = 0;

		while (m_CreateIdx < m_RowCount && inBatch < DSBX_SceneConst.SCENE_BATCH)
		{
			if (!peer.EffectGuard(m_Order))
			{
				if (m_World.GetEpoch() != m_OrderEpoch)
				{
					string stEp = "rejected";
					if (m_HadEffect)
					{
						stEp = "error";
					}
					FinishActive(peer, stEp, "stale_epoch", CurrentReadJson(m_DocId, ""));
					return;
				}
				string gReason = peer.GetGuardFailReason();
				if (!m_HadEffect)
				{
					FinishActive(peer, "rejected", gReason, CurrentReadJson(m_DocId, ""));
					return;
				}
				DSBX_SceneState stInt = m_Scene.GetSceneState(m_DocId, true);
				stInt.SetLast(m_Session, m_OpId, "scene.apply", "interrupted");
				FinishActive(peer, "error", gReason, CurrentReadJson(m_DocId, ""));
				return;
			}
			// M3: antes de cada efecto, comprobar epoch.
			if (m_World.GetEpoch() != m_OrderEpoch)
			{
				string stEp2 = "rejected";
				if (m_HadEffect)
				{
					stEp2 = "error";
				}
				FinishActive(peer, stEp2, "stale_epoch", CurrentReadJson(m_DocId, ""));
				return;
			}

			string lid = args.lid.Get(m_CreateIdx);
			int ci = args.ci.Get(m_CreateIdx);
			int xMm = args.x_mm.Get(m_CreateIdx);
			int zMm = args.z_mm.Get(m_CreateIdx);
			int yawMdeg = args.yaw_mdeg.Get(m_CreateIdx);
			string clsName = args.classes.Get(ci);

			float fx = xMm / 1000.0;
			float fz = zMm / 1000.0;
			float fyaw = yawMdeg / 1000.0;

			int gyMm = 0;
			bool gyOk = false;
			float gy = 0.0;
			if (g_Game)
			{
				gy = g_Game.SurfaceY(fx, fz);
				gyOk = DSBX_SceneWire.MetersToMmChecked(gy, -DSBX_SceneConst.MAX_Y_MM, DSBX_SceneConst.MAX_Y_MM, gyMm);
			}
			if (!gyOk)
			{
				StartInOrderCompensation(peer, inBatch);
				return;
			}

			int kind = DSBX_SceneWire.LidKind(lid);
			int flags = DSBX_SceneConst.FLAGS_ROOT;
			if (kind == 1 || kind == 2)
			{
				flags = DSBX_SceneConst.FLAGS_CREATURE;
			}
			vector targetPos = Vector(fx, gy, fz);
			Object obj = g_Game.CreateObjectEx(clsName, targetPos, flags, DSBX_SceneConst.FLAG_RF_DEFAULT);
			if (!obj)
			{
				StartInOrderCompensation(peer, inBatch);
				return;
			}
			obj.SetOrientation(Vector(fyaw, 0.0, 0.0));

			int netLow = 0;
			int netHigh = 0;
			obj.GetNetworkID(netLow, netHigh);

			DSBX_SceneState st = m_Scene.GetSceneState(m_DocId, true);
			st.EnsurePendingOrder(m_Session, m_OpId);
			st.ClearGeneration();

			m_Scene.AddRecord(m_OrderEpoch, m_DocId, m_TargetGenN, m_Session, m_OpId, lid, "", clsName, gyMm, netLow, netHigh, obj);
			RecordEffect();

			// D9 y via (a) de Q9: checkpoint en el mismo tick de la creacion.
			if (DSBX_Scene.IsMarkedForDeletion(obj) || !obj.IsAlive())
			{
				m_CheckpointRows.Insert(new DSBX_CheckpointRow(lid, -1, false, 0, 0, 0, 0, true, gyMm));
			}
			else
			{
				vector pos = obj.GetPosition();
				vector ori = obj.GetOrientation();
				int rxMm = 0;
				int ryMm = 0;
				int rzMm = 0;
				int rYawMdeg = 0;
				bool okX = DSBX_SceneWire.MetersToMmChecked(pos[0], 0, limitMm, rxMm);
				bool okY = DSBX_SceneWire.MetersToMmChecked(pos[1], -DSBX_SceneConst.MAX_Y_MM, DSBX_SceneConst.MAX_Y_MM, ryMm);
				bool okZ = DSBX_SceneWire.MetersToMmChecked(pos[2], 0, limitMm, rzMm);
				bool okYaw = DSBX_SceneWire.YawDegToMdegChecked(ori[0], rYawMdeg);
				if (okX && okY && okZ && okYaw)
				{
					int ciRead = FindClassIndex(args.classes, obj.GetType());
					m_CheckpointRows.Insert(new DSBX_CheckpointRow(lid, ciRead, true, rxMm, ryMm, rzMm, rYawMdeg, true, gyMm));
				}
				else
				{
					m_CheckpointRows.Insert(new DSBX_CheckpointRow(lid, -1, false, 0, 0, 0, 0, true, gyMm));
				}
			}

			m_CreateIdx = m_CreateIdx + 1;
			inBatch = inBatch + 1;
		}

		if (m_CreateIdx >= m_RowCount)
		{
			m_Phase = PHASE_PUBLISH;
		}
	}

	// --- Etapa 6: publicar ---

	void StepPublish(DSBX_Peer peer)
	{
		// M3: antes de publicar generation/last/pending/retained, comprobar epoch.
		if (m_World.GetEpoch() != m_OrderEpoch)
		{
			string stEp = "rejected";
			if (m_HadEffect)
			{
				stEp = "error";
			}
			FinishActive(peer, stEp, "stale_epoch", CurrentReadJson(m_DocId, ""));
			return;
		}
		DSBX_SceneState st = m_Scene.GetSceneState(m_DocId, true);
		st.m_GenN = m_TargetGenN;
		st.m_Generation = new DSBX_SceneGen(m_Session, m_OpId, m_Rev, m_DocHash, m_PlanSha256);
		st.RemovePendingOrder(m_Session, m_OpId);
		m_Scene.PrunePending(m_OrderEpoch, m_DocId);
		m_Scene.ClearRetention(st);
		st.SetCheckpoint(m_CheckpointRows);
		st.SetLast(m_Session, m_OpId, "scene.apply", "done");

		string obsJson = DSBX_SceneWire.ObsCheckpointJson(st.m_Checkpoint);
		string readJson = DSBX_SceneWire.SceneReadJson(m_OrderEpoch, m_Scene, m_DocId, obsJson);
		FinishActive(peer, "done", "", readJson);
	}
}
