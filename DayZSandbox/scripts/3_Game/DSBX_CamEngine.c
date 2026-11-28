class DSBX_CamEngine : Managed
{
	string Play(DSBX_Args args) { return "unknown_verb"; }
	string Stop() { return "unknown_verb"; }
	string ReadJson() { return ""; }
	void Tick(float timeslice) {}
}

class DSBX_CamEngineRegistry
{
	protected static ref DSBX_CamEngine s_Engine;
	static void Register(DSBX_CamEngine engine) { if (engine) s_Engine = engine; }
	static DSBX_CamEngine Get() { if (!s_Engine) s_Engine = new DSBX_CamEngine(); return s_Engine; }
}
