// F3-offline-2 §7: despacho de actor.apply, actor.reset y actor.observe al motor registrado.
// Convención de la interfaz: "" es éxito; cualquier otra cadena es el código de fallo.
// State devuelve la fila §2.1 serializada (empieza por "[") o un código de fallo.
// El camino con motor disponible es [verify] hasta que haya adaptador: con el motor base
// todo verbo de actor se rechaza con expansion_unavailable.
class DSBX_ActorOps : Managed
{
	ref array<string> m_Lids;

	void DSBX_ActorOps()
	{
		m_Lids = new array<string>();
	}

	void StartOrder(DSBX_Peer peer, DSBX_CacheEntry entry)
	{
		if (!peer || !entry || !entry.m_Order)
		{
			return;
		}
		DSBX_ActorEngine engine = DSBX_ActorEngineRegistry.Get();
		if (!engine.IsAvailable())
		{
			peer.FinishEntry(entry, "rejected", "expansion_unavailable", "{}");
			return;
		}
		string verb = entry.m_Order.verb;
		DSBX_Args args = entry.m_Order.args;
		if (verb == "actor.apply")
		{
			Apply(peer, entry, engine, args);
			return;
		}
		if (verb == "actor.reset")
		{
			Reset(peer, entry, engine);
			return;
		}
		if (verb == "actor.observe")
		{
			string body = ReadJson(engine, "");
			peer.FinishEntry(entry, "done", "", body);
			return;
		}
		peer.FinishEntry(entry, "rejected", "unknown_verb", "{}");
	}

	protected void Apply(DSBX_Peer peer, DSBX_CacheEntry entry, DSBX_ActorEngine engine, DSBX_Args args)
	{
		if (!args.a_items || !args.mk_x_mm || !args.mk_z_mm || !args.g_emote || !args.g_at || !args.g_t_ms)
		{
			peer.FinishEntry(entry, "rejected", "bad_args", "{}");
			return;
		}
		if (args.mk_x_mm.Count() != args.mk_z_mm.Count() || args.g_emote.Count() != args.g_at.Count() || args.g_emote.Count() != args.g_t_ms.Count())
		{
			peer.FinishEntry(entry, "rejected", "bad_args", "{}");
			return;
		}
		vector pos = Vector(args.a_x_mm / 1000.0, 0, args.a_z_mm / 1000.0);
		float yaw = args.a_yaw_mdeg / 1000.0;
		string res = engine.Spawn(args.a_lid, args.a_cls, pos, yaw, args.a_items);
		if (res != "")
		{
			peer.FinishEntry(entry, "error", res, "{}");
			return;
		}
		if (m_Lids.Find(args.a_lid) < 0)
		{
			m_Lids.Insert(args.a_lid);
		}
		array<vector> marks = new array<vector>();
		for (int k = 0; k < args.mk_x_mm.Count(); k++)
		{
			marks.Insert(Vector(args.mk_x_mm[k] / 1000.0, 0, args.mk_z_mm[k] / 1000.0));
		}
		res = engine.SetMarks(args.a_lid, marks, args.a_behaviour, args.a_roam_mm / 1000.0);
		if (res != "")
		{
			peer.FinishEntry(entry, "error", res, "{}");
			return;
		}
		// [verify S3] el momento del gesto (g_at, g_t_ms) lo respeta el adaptador.
		for (int gi = 0; gi < args.g_emote.Count(); gi++)
		{
			res = engine.RequestGesture(args.a_lid, gi, args.g_emote[gi]);
			if (res != "")
			{
				peer.FinishEntry(entry, "error", res, "{}");
				return;
			}
		}
		string body = ReadJson(engine, args.a_lid);
		peer.FinishEntry(entry, "done", "", body);
	}

	protected void Reset(DSBX_Peer peer, DSBX_CacheEntry entry, DSBX_ActorEngine engine)
	{
		array<string> kept = new array<string>();
		foreach (string lid : m_Lids)
		{
			string res = engine.Despawn(lid);
			if (res != "")
			{
				kept.Insert(lid);
			}
		}
		m_Lids = kept;
		string body = ReadJson(engine, "");
		peer.FinishEntry(entry, "done", "", body);
	}

	// Foto §2.3 de la parte 1: las filas de los actores vivos del registro y gestures vacío
	// (los eventos de gesto son del adaptador, [verify S3]). Con `only`, solo esa fila.
	protected string ReadJson(DSBX_ActorEngine engine, string only)
	{
		string rows = "";
		foreach (string lid : m_Lids)
		{
			if (only != "" && lid != only)
			{
				continue;
			}
			string row = engine.State(lid);
			if (row.Length() == 0 || row.Get(0) != "[")
			{
				continue;
			}
			if (rows != "")
			{
				rows = rows + ",";
			}
			rows = rows + row;
		}
		return "{\"actors\":[" + rows + "],\"gestures\":[]}";
	}
}
