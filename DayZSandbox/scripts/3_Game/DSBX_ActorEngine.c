class DSBX_ActorEngine : Managed
{
	string Name() { return "none"; }
	bool IsAvailable() { return false; }
	// Las operaciones del plan §3 F3 (spawn, marks, behaviour, gesture y state) más parar y retirar;
	// la base devuelve el código "expansion_unavailable". State devuelve la fila de §2.1 serializada.
	string Spawn(string lid, string cls, vector pos, float yaw, array<string> items) { return "expansion_unavailable"; }
	string SetMarks(string lid, array<vector> marks, string behaviour, float roam) { return "expansion_unavailable"; }
	string RequestGesture(string lid, int gi, string emote) { return "expansion_unavailable"; }
	string State(string lid) { return "expansion_unavailable"; }
	string Stop(string lid) { return "expansion_unavailable"; }
	string Despawn(string lid) { return "expansion_unavailable"; }
}

class DSBX_ActorEngineRegistry
{
	protected static ref DSBX_ActorEngine s_Engine;
	static void Register(DSBX_ActorEngine engine) { if (engine) s_Engine = engine; }
	static DSBX_ActorEngine Get() { if (!s_Engine) s_Engine = new DSBX_ActorEngine(); return s_Engine; }
	static string EngineName() { if (Get().IsAvailable()) return Get().Name(); return "none"; }
}
