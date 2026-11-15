// Adaptador de Expansion AI para el spike S3. Símbolos reanclados contra las fuentes de DayZ-Expansion-AI
// 1.9.84 (workshop 2792982069, ai_scripts): eAIGroup.c:123 (CreateGroup), :213 (AddWaypoint), :236
// (GetCurrentWaypoint), :241 (ClearWaypoints), :251 (SetWaypointBehaviour), :633 (SetFaction), :671 (GetFaction),
// eAIBase.c:313 (m_eAI_TargetPositionIsFinal), :347 (m_Expansion_EmoteID), :3926 (SetGroup), :10860
// (Expansion_SetEmote), eAIFactionPassive.c, eAIFactionRaiders.c y AIenums.c:1-13 (eAIWaypointBehavior).
#ifdef EXPANSIONMODAI
modded class eAIBase
{
	// Lee el miembro real donde Expansion_SetEmote guarda el gesto pendiente: sin espejo y sin ponerlo a 0 al
	// ejecutar Expansion_PlayEmote (sin autoCancel Expansion no lo limpia, eAIBase.c:10862-10867,10920-10921).
	int DsbxGetPendingEmoteID()
	{
		return m_Expansion_EmoteID;
	}

	// Último isFinal que el FSM pasó a OverrideTargetPosition (eAIBase.c:5005).
	bool DsbxGetTargetPositionIsFinal()
	{
		return m_eAI_TargetPositionIsFinal;
	}
}

class DSBX_QA_ExpansionBackend : DSBX_QA_ActorBackend
{
	override bool IsAvailable()
	{
		return true;
	}

	override string ResolveActorClass(string character)
	{
		if (character == "")
		{
			return "";
		}
		// Clase fija "eAI_" + nombre vanilla (eAISurvivor.c): nunca GetQuasiRandom().
		string cls = "eAI_" + character;
		if (!g_Game.ConfigIsExisting("CfgVehicles " + cls))
		{
			return "";
		}
		return cls;
	}

	override PlayerBase CreateActor(string actorClass, vector pos)
	{
		vector p = pos;
		p[1] = g_Game.SurfaceY(pos[0], pos[2]);
		// Sin ECE_DYNAMIC_PERSISTENCY (centraleconomy.c:33): el actor no persiste (#11).
		int flags = ECE_PLACE_ON_SURFACE | ECE_INITAI | ECE_NOLIFETIME | ECE_NOPERSISTENCY_WORLD;
		eAIBase ai = eAIBase.Cast(g_Game.CreateObjectEx(actorClass, p, flags));
		if (!ai)
		{
			return null;
		}
		// Un grupo por actor y facción pasiva (las marcas son del grupo).
		eAIFaction passive = new eAIFactionPassive();
		eAIGroup group = eAIGroup.CreateGroup(passive);
		ai.SetGroup(group);
		return ai;
	}

	override void ReleaseActor(PlayerBase actor)
	{
		eAIBase ai = eAIBase.Cast(actor);
		if (!ai)
		{
			return;
		}
		eAIGroup group = ai.GetGroup();
		if (group)
		{
			group.ClearWaypoints();
			group.Delete();
		}
	}

	override bool SetPassive(PlayerBase actor)
	{
		eAIBase ai = eAIBase.Cast(actor);
		if (!ai || !ai.GetGroup())
		{
			return false;
		}
		eAIFaction passive = new eAIFactionPassive();
		ai.GetGroup().SetFaction(passive);
		return true;
	}

	override bool SetHostile(PlayerBase actor, string factionKey)
	{
		eAIBase ai = eAIBase.Cast(actor);
		if (!ai || !ai.GetGroup())
		{
			return false;
		}
		// Facción de QA: Raiders (no es amiga de infectados ni de otros grupos, eAIFactionRaiders.c).
		if (factionKey != "qa_hostile")
		{
			return false;
		}
		eAIFaction hostile = new eAIFactionRaiders();
		ai.GetGroup().SetFaction(hostile);
		return true;
	}

	override string FactionClass(PlayerBase actor)
	{
		eAIBase ai = eAIBase.Cast(actor);
		if (!ai || !ai.GetGroup())
		{
			return "";
		}
		eAIFaction f = ai.GetGroup().GetFaction();
		if (!f)
		{
			return "";
		}
		return f.Type().ToString();
	}

	override bool ClearWaypoints(PlayerBase actor)
	{
		eAIBase ai = eAIBase.Cast(actor);
		if (!ai || !ai.GetGroup())
		{
			return false;
		}
		ai.GetGroup().ClearWaypoints();
		return true;
	}

	override bool AddWaypoint(PlayerBase actor, vector pos)
	{
		eAIBase ai = eAIBase.Cast(actor);
		if (!ai || !ai.GetGroup())
		{
			return false;
		}
		vector p = pos;
		p[1] = g_Game.SurfaceY(pos[0], pos[2]);
		ai.GetGroup().AddWaypoint(p);
		return true;
	}

	override bool SetBehaviour(PlayerBase actor, string mode)
	{
		eAIBase ai = eAIBase.Cast(actor);
		if (!ai || !ai.GetGroup())
		{
			return false;
		}
		// Nunca ROAMING ni ROAMING_LOCAL (CX-02): el deambular acotado es propio de Sandbox.
		if (mode == "HALT")
		{
			ai.GetGroup().SetWaypointBehaviour(eAIWaypointBehavior.HALT);
			return true;
		}
		if (mode == "ONCE")
		{
			ai.GetGroup().SetWaypointBehaviour(eAIWaypointBehavior.ONCE);
			return true;
		}
		if (mode == "LOOP")
		{
			ai.GetGroup().SetWaypointBehaviour(eAIWaypointBehavior.LOOP);
			return true;
		}
		return false;
	}

	override vector CurrentWaypoint(PlayerBase actor)
	{
		eAIBase ai = eAIBase.Cast(actor);
		if (!ai || !ai.GetGroup())
		{
			return vector.Zero;
		}
		return ai.GetGroup().GetCurrentWaypoint();
	}

	override bool TargetPositionIsFinal(PlayerBase actor)
	{
		eAIBase ai = eAIBase.Cast(actor);
		if (!ai)
		{
			return false;
		}
		return ai.DsbxGetTargetPositionIsFinal();
	}

	override void SetEmote(PlayerBase actor, int emoteId)
	{
		eAIBase ai = eAIBase.Cast(actor);
		if (!ai)
		{
			return;
		}
		// Sin autoCancel: la petición queda pendiente hasta que el FSM pueda ejecutarla o la retiremos con id 0.
		ai.Expansion_SetEmote(emoteId, false, 0);
	}

	override int PendingEmote(PlayerBase actor)
	{
		eAIBase ai = eAIBase.Cast(actor);
		if (!ai)
		{
			return 0;
		}
		return ai.DsbxGetPendingEmoteID();
	}
}
#endif
