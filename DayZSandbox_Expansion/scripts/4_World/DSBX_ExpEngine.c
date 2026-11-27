#ifdef EXPANSIONMODAI
class DSBX_ExpConst
{
	static const float REACH_M = 1.5;
	static const float STUCK_M = 0.25;
	static const int STUCK_MS = 5000;
	static const int ROAM_PAUSE_MS = 1500;
	static const int ROAM_GIVEUP_MS = 60000;
	static const int START_TIMEOUT_MS = 5000;
	static const int PLAY_TIMEOUT_MS = 30000;
}

class DSBX_ExpGesture : Managed
{
	int m_Gi;
	int m_EmoteId;
	int m_AtMark;
	int m_TMs;
	string m_St;
	int m_CbSnap;
	int m_BoundInst;
	float m_RequestedMs;
	float m_PlayingMs;
}

class DSBX_ExpEvent : Managed
{
	int m_Gi;
	string m_St;
	int m_TMs;
	string m_Cause;
}

class DSBX_ExpActor : Managed
{
	eAIBase m_Ai;
	string m_Lid;
	string m_Cls;
	vector m_P0;
	float m_CreatedMs;
	ref array<vector> m_Marks;
	string m_Behaviour;
	float m_Roam;
	int m_MarkI;
	string m_MarkSt;
	ref array<int> m_Reached;
	vector m_LastPos;
	float m_LastMoveMs;
	int m_Prng;
	vector m_RoamDest;
	float m_RoamSentMs;
	float m_RoamPauseUntil;
	bool m_RoamInPause;
	ref array<ref DSBX_ExpGesture> m_Gestures;
	ref array<ref DSBX_ExpEvent> m_Events;
}

class DSBX_ExpEmoteHub
{
	protected static DSBX_ExpansionEngine s_Engine;

	static void SetEngine(DSBX_ExpansionEngine engine)
	{
		s_Engine = engine;
	}

	static DSBX_ExpansionEngine GetEngine()
	{
		return s_Engine;
	}
}

class DSBX_ExpansionEngine : DSBX_ActorEngine
{
	protected ref map<string, ref DSBX_ExpActor> m_Actors;

	void DSBX_ExpansionEngine()
	{
		m_Actors = new map<string, ref DSBX_ExpActor>();
		DSBX_ExpEmoteHub.SetEngine(this);
	}

	override string Name()
	{
		return "expansion";
	}

	override bool IsAvailable()
	{
		return true;
	}

	float NowMs()
	{
		return g_Game.GetTickTime() * 1000.0;
	}

	int TickInt()
	{
		return (int)NowMs();
	}

	int SeedLid(string lid)
	{
		int seed = 0;
		int i = 0;
		while (i < lid.Length())
		{
			string ch = lid.Substring(i, 1);
			int c = ch.ToAscii();
			seed = seed + c;
			i = i + 1;
		}
		return seed;
	}

	float NextRnd(DSBX_ExpActor rec)
	{
		rec.m_Prng = (rec.m_Prng * 75 + 74) % 65537;
		return rec.m_Prng / 65537.0;
	}

	float DistXZ(vector a, vector b)
	{
		float dx = a[0] - b[0];
		float dz = a[2] - b[2];
		return Math.Sqrt(dx * dx + dz * dz);
	}

	int EmoteId(string emote)
	{
		if (emote == "EmoteGreeting") return EmoteConstants.ID_EMOTE_GREETING;
		if (emote == "EmotePoint") return EmoteConstants.ID_EMOTE_POINT;
		if (emote == "EmoteThumb") return EmoteConstants.ID_EMOTE_THUMB;
		if (emote == "EmoteSurrender") return EmoteConstants.ID_EMOTE_SURRENDER;
		if (emote == "EmoteSalute") return EmoteConstants.ID_EMOTE_SALUTE;
		if (emote == "EmoteFacepalm") return EmoteConstants.ID_EMOTE_FACEPALM;
		if (emote == "EmoteTaunt") return EmoteConstants.ID_EMOTE_TAUNT;
		if (emote == "EmoteHeart") return EmoteConstants.ID_EMOTE_HEART;
		return -1;
	}

	void SweepAttachments(eAIBase ai)
	{
		if (!ai || !ai.GetInventory())
		{
			return;
		}
		GameInventory inv = ai.GetInventory();
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
		int j = 0;
		while (j < found.Count())
		{
			EntityAI victim = found.Get(j);
			if (!inv.LocalDestroyEntity(victim))
			{
				g_Game.ObjectDelete(victim);
			}
			j = j + 1;
		}
	}

	void HaltGroup(eAIBase ai)
	{
		if (!ai)
		{
			return;
		}
		eAIGroup group = ai.GetGroup();
		if (!group)
		{
			return;
		}
		group.ClearWaypoints();
		group.SetWaypointBehaviour(eAIWaypointBehavior.HALT);
	}

	void Emit(DSBX_ExpActor rec, int gi, string st, string cause)
	{
		DSBX_ExpEvent ev = new DSBX_ExpEvent();
		ev.m_Gi = gi;
		ev.m_St = st;
		ev.m_TMs = TickInt();
		ev.m_Cause = cause;
		rec.m_Events.Insert(ev);
	}

	void ClearEmote(eAIBase ai)
	{
		if (!ai)
		{
			return;
		}
		ai.Expansion_SetEmote(0, false, 0);
	}

	void FinishGesture(DSBX_ExpActor rec, DSBX_ExpGesture g, string st, string cause)
	{
		Emit(rec, g.m_Gi, st, cause);
		g.m_St = "done";
		g.m_BoundInst = 0;
		ClearEmote(rec.m_Ai);
	}

	void CancelActive(DSBX_ExpActor rec, string cause)
	{
		int i = 0;
		while (i < rec.m_Gestures.Count())
		{
			DSBX_ExpGesture g = rec.m_Gestures.Get(i);
			if (g.m_St == "requested" || g.m_St == "playing")
			{
				FinishGesture(rec, g, "canceled", cause);
			}
			else if (g.m_St == "queued")
			{
				g.m_St = "done";
			}
			i = i + 1;
		}
	}

	bool HasBusyGesture(DSBX_ExpActor rec)
	{
		int i = 0;
		while (i < rec.m_Gestures.Count())
		{
			DSBX_ExpGesture g = rec.m_Gestures.Get(i);
			if (g.m_St == "requested" || g.m_St == "playing")
			{
				return true;
			}
			i = i + 1;
		}
		return false;
	}

	bool TriggerReady(DSBX_ExpActor rec, DSBX_ExpGesture g)
	{
		if (g.m_AtMark >= 0)
		{
			if (g.m_AtMark < rec.m_Reached.Count() && rec.m_Reached.Get(g.m_AtMark) == 1)
			{
				return true;
			}
			return false;
		}
		if (g.m_TMs >= 0)
		{
			float elapsed = NowMs() - rec.m_CreatedMs;
			if (elapsed >= g.m_TMs)
			{
				return true;
			}
		}
		return false;
	}

	void FireGesture(DSBX_ExpActor rec, DSBX_ExpGesture g)
	{
		if (!rec.m_Ai)
		{
			return;
		}
		g.m_CbSnap = EmoteCB.DsbxCbCounter();
		g.m_BoundInst = 0;
		g.m_RequestedMs = NowMs();
		g.m_St = "requested";
		rec.m_Ai.Expansion_SetEmote(g.m_EmoteId, false, 0);
		Emit(rec, g.m_Gi, "requested", "");
	}

	void SendRoamDest(DSBX_ExpActor rec)
	{
		if (!rec.m_Ai || !rec.m_Ai.GetGroup())
		{
			return;
		}
		float ang = Math.PI2 * NextRnd(rec);
		float frac = 0.35 + 0.4 * NextRnd(rec);
		float dist = rec.m_Roam * frac;
		vector dest = Vector(rec.m_P0[0] + Math.Cos(ang) * dist, 0.0, rec.m_P0[2] + Math.Sin(ang) * dist);
		dest[1] = g_Game.SurfaceY(dest[0], dest[2]);
		rec.m_RoamDest = dest;
		rec.m_RoamSentMs = NowMs();
		rec.m_RoamInPause = false;
		rec.m_MarkI = -1;
		rec.m_MarkSt = "moving";
		eAIGroup group = rec.m_Ai.GetGroup();
		group.ClearWaypoints();
		group.AddWaypoint(dest);
		group.SetWaypointBehaviour(eAIWaypointBehavior.ONCE);
	}

	void MarkReached(DSBX_ExpActor rec, int idx)
	{
		while (rec.m_Reached.Count() <= idx)
		{
			rec.m_Reached.Insert(0);
		}
		rec.m_Reached.Set(idx, 1);
	}

	override string Spawn(string lid, string cls, vector pos, float yaw, array<string> items)
	{
		if (m_Actors.Get(lid))
		{
			Despawn(lid);
		}
		string engineCls = "eAI_" + cls;
		string cfgPath = "CfgVehicles " + engineCls;
		if (!g_Game.ConfigIsExisting(cfgPath))
		{
			return "unknown_class";
		}
		vector p = pos;
		p[1] = g_Game.SurfaceY(pos[0], pos[2]);
		int flags = ECE_PLACE_ON_SURFACE | ECE_INITAI | ECE_NOLIFETIME | ECE_NOPERSISTENCY_WORLD;
		eAIBase ai = eAIBase.Cast(g_Game.CreateObjectEx(engineCls, p, flags));
		if (!ai)
		{
			return "spawn_failed";
		}
		ai.SetOrientation(Vector(yaw, 0, 0));
		eAIFaction passive = new eAIFactionPassive();
		eAIGroup group = eAIGroup.CreateGroup(passive);
		ai.SetGroup(group);
		SweepAttachments(ai);
		DSBX_ExpActor rec = new DSBX_ExpActor();
		rec.m_Ai = ai;
		rec.m_Lid = lid;
		rec.m_Cls = cls;
		rec.m_P0 = ai.GetPosition();
		rec.m_CreatedMs = NowMs();
		rec.m_Marks = new array<vector>();
		rec.m_Behaviour = "HOLD";
		rec.m_Roam = 0;
		rec.m_MarkI = -1;
		rec.m_MarkSt = "idle";
		rec.m_Reached = new array<int>();
		rec.m_LastPos = rec.m_P0;
		rec.m_LastMoveMs = rec.m_CreatedMs;
		rec.m_Prng = SeedLid(lid);
		rec.m_Gestures = new array<ref DSBX_ExpGesture>();
		rec.m_Events = new array<ref DSBX_ExpEvent>();
		m_Actors.Set(lid, rec);
		if (items)
		{
			int i = 0;
			while (i < items.Count())
			{
				string itemClass = items.Get(i);
				EntityAI dressed = ai.GetInventory().CreateAttachment(itemClass);
				if (!dressed)
				{
					Despawn(lid);
					return "wardrobe_failed";
				}
				i = i + 1;
			}
		}
		return "";
	}

	override string SetMarks(string lid, array<vector> marks, string behaviour, float roam)
	{
		DSBX_ExpActor rec = m_Actors.Get(lid);
		if (!rec)
		{
			return "unknown_actor";
		}
		if (behaviour != "HOLD" && behaviour != "ONCE" && behaviour != "LOOP" && behaviour != "ROAM")
		{
			return "bad_behaviour";
		}
		if ((behaviour == "ONCE" || behaviour == "LOOP") && (!marks || marks.Count() == 0))
		{
			return "bad_marks";
		}
		rec.m_Marks = new array<vector>();
		rec.m_Reached = new array<int>();
		if (marks)
		{
			int i = 0;
			while (i < marks.Count())
			{
				vector m = marks.Get(i);
				m[1] = g_Game.SurfaceY(m[0], m[2]);
				rec.m_Marks.Insert(m);
				rec.m_Reached.Insert(0);
				i = i + 1;
			}
		}
		rec.m_Behaviour = behaviour;
		rec.m_Roam = roam;
		if (!rec.m_Ai || !rec.m_Ai.GetGroup())
		{
			return "";
		}
		eAIGroup group = rec.m_Ai.GetGroup();
		group.ClearWaypoints();
		if (behaviour == "HOLD")
		{
			group.SetWaypointBehaviour(eAIWaypointBehavior.HALT);
			rec.m_MarkI = -1;
			rec.m_MarkSt = "idle";
			return "";
		}
		if (behaviour == "ROAM")
		{
			rec.m_Prng = SeedLid(lid);
			rec.m_MarkI = -1;
			SendRoamDest(rec);
			return "";
		}
		int k = 0;
		while (k < rec.m_Marks.Count())
		{
			group.AddWaypoint(rec.m_Marks.Get(k));
			k = k + 1;
		}
		if (behaviour == "ONCE")
		{
			group.SetWaypointBehaviour(eAIWaypointBehavior.ONCE);
		}
		else
		{
			group.SetWaypointBehaviour(eAIWaypointBehavior.LOOP);
		}
		rec.m_MarkI = 0;
		rec.m_MarkSt = "moving";
		rec.m_LastPos = rec.m_Ai.GetPosition();
		rec.m_LastMoveMs = NowMs();
		return "";
	}

	override string RequestGesture(string lid, int gi, string emote, int atMark, int tMs)
	{
		DSBX_ExpActor rec = m_Actors.Get(lid);
		if (!rec)
		{
			return "unknown_actor";
		}
		int emoteId = EmoteId(emote);
		if (emoteId < 0)
		{
			return "unknown_emote";
		}
		DSBX_ExpGesture g = new DSBX_ExpGesture();
		g.m_Gi = gi;
		g.m_EmoteId = emoteId;
		g.m_AtMark = atMark;
		g.m_TMs = tMs;
		g.m_St = "queued";
		g.m_CbSnap = 0;
		g.m_BoundInst = 0;
		rec.m_Gestures.Insert(g);
		return "";
	}

	override string Gestures(string lid)
	{
		DSBX_ExpActor rec = m_Actors.Get(lid);
		if (!rec)
		{
			return "";
		}
		string acc = "";
		int i = 0;
		while (i < rec.m_Events.Count())
		{
			DSBX_ExpEvent ev = rec.m_Events.Get(i);
			string lidJson = DSBX_Wire.WireText(rec.m_Lid);
			string stJson = DSBX_Wire.WireText(ev.m_St);
			string giJson = ev.m_Gi.ToString();
			string tJson = ev.m_TMs.ToString();
			string causeJson = "null";
			if (ev.m_Cause != "")
			{
				causeJson = DSBX_Wire.WireText(ev.m_Cause);
			}
			string piece = "[" + lidJson + "," + giJson + "," + stJson + "," + tJson + "," + causeJson + "]";
			if (acc != "")
			{
				acc = acc + ",";
			}
			acc = acc + piece;
			i = i + 1;
		}
		return acc;
	}

	override string State(string lid)
	{
		DSBX_ExpActor rec = m_Actors.Get(lid);
		if (!rec)
		{
			return "unknown_actor";
		}
		int tMs = TickInt();
		string tJson = tMs.ToString();
		string lidJson = DSBX_Wire.WireText(lid);
		if (!rec.m_Ai || !rec.m_Ai.IsAlive())
		{
			return "[" + lidJson + ",null,null,null,null,null,[],-1,\"idle\"," + tJson + "]";
		}
		vector pos = rec.m_Ai.GetPosition();
		vector ori = rec.m_Ai.GetOrientation();
		int xMm = 0;
		int yMm = 0;
		int zMm = 0;
		int yawMdeg = 0;
		bool okX = DSBX_SceneWire.MetersToMmChecked(pos[0], 0, DSBX_SceneConst.MAX_XZ_MM, xMm);
		bool okY = DSBX_SceneWire.MetersToMmChecked(pos[1], -DSBX_SceneConst.MAX_Y_MM, DSBX_SceneConst.MAX_Y_MM, yMm);
		bool okZ = DSBX_SceneWire.MetersToMmChecked(pos[2], 0, DSBX_SceneConst.MAX_XZ_MM, zMm);
		bool okYaw = DSBX_SceneWire.YawDegToMdegChecked(ori[0], yawMdeg);
		if (!okX || !okY || !okZ || !okYaw)
		{
			return "bad_position";
		}
		string itemsJson = "";
		if (rec.m_Ai.GetInventory())
		{
			GameInventory inv = rec.m_Ai.GetInventory();
			int n = inv.AttachmentCount();
			int i = 0;
			while (i < n)
			{
				EntityAI att = inv.GetAttachmentFromIndex(i);
				if (att)
				{
					string typ = att.GetType();
					string itemJson = DSBX_Wire.WireText(typ);
					if (itemsJson != "")
					{
						itemsJson = itemsJson + ",";
					}
					itemsJson = itemsJson + itemJson;
				}
				i = i + 1;
			}
		}
		string clsJson = DSBX_Wire.WireText(rec.m_Cls);
		string xJson = xMm.ToString();
		string yJson = yMm.ToString();
		string zJson = zMm.ToString();
		string yawJson = yawMdeg.ToString();
		string miJson = rec.m_MarkI.ToString();
		string stJson = DSBX_Wire.WireText(rec.m_MarkSt);
		// En cuatro pasos: una sola concatenación de 21 términos da ES-FORMULA-TOO-COMPLEX en el linter.
		string row = "[" + lidJson + "," + clsJson + ",";
		row = row + xJson + "," + yJson + "," + zJson + ",";
		row = row + yawJson + ",[" + itemsJson + "],";
		row = row + miJson + "," + stJson + "," + tJson + "]";
		return row;
	}

	override string Stop(string lid)
	{
		DSBX_ExpActor rec = m_Actors.Get(lid);
		if (!rec)
		{
			return "unknown_actor";
		}
		HaltGroup(rec.m_Ai);
		rec.m_MarkI = -1;
		rec.m_MarkSt = "idle";
		rec.m_Behaviour = "HOLD";
		CancelActive(rec, "stop");
		return "";
	}

	override string Despawn(string lid)
	{
		DSBX_ExpActor rec = m_Actors.Get(lid);
		if (!rec)
		{
			return "";
		}
		HaltGroup(rec.m_Ai);
		rec.m_MarkI = -1;
		rec.m_MarkSt = "idle";
		CancelActive(rec, "stop");
		if (rec.m_Ai)
		{
			eAIGroup group = rec.m_Ai.GetGroup();
			if (group)
			{
				group.ClearWaypoints();
				group.Delete();
			}
			g_Game.ObjectDelete(rec.m_Ai);
			rec.m_Ai = null;
		}
		m_Actors.Remove(lid);
		return "";
	}

	void TickMarks(DSBX_ExpActor rec, vector pos)
	{
		if (rec.m_Behaviour != "ONCE" && rec.m_Behaviour != "LOOP")
		{
			return;
		}
		if (rec.m_MarkI < 0 || rec.m_MarkI >= rec.m_Marks.Count())
		{
			return;
		}
		if (rec.m_MarkSt == "arrived")
		{
			return;
		}
		vector mark = rec.m_Marks.Get(rec.m_MarkI);
		if (DistXZ(pos, mark) < DSBX_ExpConst.REACH_M)
		{
			MarkReached(rec, rec.m_MarkI);
			if (rec.m_Behaviour == "ONCE")
			{
				if (rec.m_MarkI >= rec.m_Marks.Count() - 1)
				{
					rec.m_MarkSt = "arrived";
				}
				else
				{
					rec.m_MarkI = rec.m_MarkI + 1;
					rec.m_MarkSt = "moving";
				}
			}
			else
			{
				rec.m_MarkI = (rec.m_MarkI + 1) % rec.m_Marks.Count();
				rec.m_MarkSt = "moving";
			}
			rec.m_LastPos = pos;
			rec.m_LastMoveMs = NowMs();
			return;
		}
		if (DistXZ(pos, rec.m_LastPos) >= DSBX_ExpConst.STUCK_M)
		{
			rec.m_LastPos = pos;
			rec.m_LastMoveMs = NowMs();
			if (rec.m_MarkSt == "unreachable")
			{
				rec.m_MarkSt = "moving";
			}
		}
		else
		{
			if (NowMs() - rec.m_LastMoveMs >= DSBX_ExpConst.STUCK_MS)
			{
				rec.m_MarkSt = "unreachable";
			}
		}
	}

	void TickRoam(DSBX_ExpActor rec, vector pos)
	{
		if (rec.m_Behaviour != "ROAM")
		{
			return;
		}
		rec.m_MarkI = -1;
		if (rec.m_RoamInPause)
		{
			rec.m_MarkSt = "idle";
			if (NowMs() >= rec.m_RoamPauseUntil)
			{
				SendRoamDest(rec);
			}
			return;
		}
		if (DistXZ(pos, rec.m_RoamDest) < DSBX_ExpConst.REACH_M)
		{
			rec.m_MarkSt = "idle";
			rec.m_RoamInPause = true;
			rec.m_RoamPauseUntil = NowMs() + DSBX_ExpConst.ROAM_PAUSE_MS;
			return;
		}
		if (NowMs() - rec.m_RoamSentMs >= DSBX_ExpConst.ROAM_GIVEUP_MS)
		{
			SendRoamDest(rec);
		}
	}

	void TickGestures(DSBX_ExpActor rec)
	{
		float now = NowMs();
		int i = 0;
		while (i < rec.m_Gestures.Count())
		{
			DSBX_ExpGesture g = rec.m_Gestures.Get(i);
			if (g.m_St == "requested")
			{
				if (now - g.m_RequestedMs >= DSBX_ExpConst.START_TIMEOUT_MS)
				{
					FinishGesture(rec, g, "expired", "timeout");
				}
			}
			else if (g.m_St == "playing")
			{
				if (now - g.m_PlayingMs >= DSBX_ExpConst.PLAY_TIMEOUT_MS)
				{
					FinishGesture(rec, g, "expired", "timeout");
				}
			}
			i = i + 1;
		}
		if (HasBusyGesture(rec))
		{
			return;
		}
		int best = -1;
		int bestGi = 0;
		int j = 0;
		while (j < rec.m_Gestures.Count())
		{
			DSBX_ExpGesture cand = rec.m_Gestures.Get(j);
			if (cand.m_St == "queued" && TriggerReady(rec, cand))
			{
				if (best < 0 || cand.m_Gi < bestGi)
				{
					best = j;
					bestGi = cand.m_Gi;
				}
			}
			j = j + 1;
		}
		if (best >= 0)
		{
			FireGesture(rec, rec.m_Gestures.Get(best));
		}
	}

	void Tick(float timeslice)
	{
		foreach (string lid, DSBX_ExpActor rec : m_Actors)
		{
			if (!rec || !rec.m_Ai || !rec.m_Ai.IsAlive())
			{
				continue;
			}
			vector pos = rec.m_Ai.GetPosition();
			TickMarks(rec, pos);
			TickRoam(rec, pos);
			TickGestures(rec);
		}
	}

	DSBX_ExpActor FindByPlayer(PlayerBase player)
	{
		if (!player)
		{
			return null;
		}
		foreach (string lid, DSBX_ExpActor rec : m_Actors)
		{
			if (rec && rec.m_Ai == player)
			{
				return rec;
			}
		}
		return null;
	}

	DSBX_ExpGesture FindBound(DSBX_ExpActor rec, int cbInstId)
	{
		int i = 0;
		while (i < rec.m_Gestures.Count())
		{
			DSBX_ExpGesture g = rec.m_Gestures.Get(i);
			if (g.m_BoundInst == cbInstId && (g.m_St == "requested" || g.m_St == "playing"))
			{
				return g;
			}
			i = i + 1;
		}
		return null;
	}

	void OnBound(PlayerBase player, int cbInstId, int gestureId, int cmdId)
	{
		DSBX_ExpActor rec = FindByPlayer(player);
		if (!rec)
		{
			return;
		}
		int i = 0;
		while (i < rec.m_Gestures.Count())
		{
			DSBX_ExpGesture g = rec.m_Gestures.Get(i);
			if (g.m_St == "requested" && g.m_EmoteId == gestureId && cbInstId > g.m_CbSnap)
			{
				g.m_BoundInst = cbInstId;
				return;
			}
			i = i + 1;
		}
	}

	void OnState(PlayerBase player, int cbInstId, int oldState, int newState)
	{
		DSBX_ExpActor rec = FindByPlayer(player);
		if (!rec)
		{
			return;
		}
		DSBX_ExpGesture g = FindBound(rec, cbInstId);
		if (!g)
		{
			return;
		}
		if (g.m_St == "requested" && oldState == 0 && newState != 0)
		{
			g.m_St = "playing";
			g.m_PlayingMs = NowMs();
			Emit(rec, g.m_Gi, "playing", "");
		}
	}

	void OnFinish(PlayerBase player, int cbInstId, bool pCanceled)
	{
		DSBX_ExpActor rec = FindByPlayer(player);
		if (!rec)
		{
			return;
		}
		DSBX_ExpGesture g = FindBound(rec, cbInstId);
		if (!g)
		{
			return;
		}
		if (pCanceled)
		{
			FinishGesture(rec, g, "canceled", "interrupted");
		}
		else
		{
			FinishGesture(rec, g, "finished", "");
		}
	}
}

modded class EmoteCB
{
	protected static int s_DsbxNextCbInstId;
	protected int m_DsbxCbInstId;

	static int DsbxCbCounter()
	{
		return s_DsbxNextCbInstId;
	}

	void DsbxOnBound(PlayerBase player, EmoteManager mgr, int gestureId, int cmdId)
	{
		if (m_DsbxCbInstId == 0)
		{
			s_DsbxNextCbInstId = s_DsbxNextCbInstId + 1;
			m_DsbxCbInstId = s_DsbxNextCbInstId;
		}
		EnableStateChangeCallback();
		DSBX_ExpansionEngine engine = DSBX_ExpEmoteHub.GetEngine();
		if (engine)
		{
			engine.OnBound(player, m_DsbxCbInstId, gestureId, cmdId);
		}
	}

	override void OnStateChange(int pOldState, int pCurrentState)
	{
		super.OnStateChange(pOldState, pCurrentState);
		DSBX_ExpansionEngine engine = DSBX_ExpEmoteHub.GetEngine();
		if (engine)
		{
			engine.OnState(m_player, m_DsbxCbInstId, pOldState, pCurrentState);
		}
	}

	override void OnFinish(bool pCanceled)
	{
		super.OnFinish(pCanceled);
		DSBX_ExpansionEngine engine = DSBX_ExpEmoteHub.GetEngine();
		if (engine)
		{
			engine.OnFinish(m_player, m_DsbxCbInstId, pCanceled);
		}
	}
}

modded class EmoteManager
{
	override protected void CreateEmoteCallback(typename callbacktype, int id, int mask, bool fullbody)
	{
		super.CreateEmoteCallback(callbacktype, id, mask, fullbody);
		if (m_Callback)
		{
			m_Callback.DsbxOnBound(m_Player, this, m_CurrentGestureID, id);
		}
	}
}
#endif
