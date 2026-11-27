#ifdef EXPANSIONMODAI
modded class MissionServer
{
	protected ref DSBX_ExpansionEngine m_DsbxExpEngine;

	override void OnMissionStart()
	{
		super.OnMissionStart();
		m_DsbxExpEngine = new DSBX_ExpansionEngine();
		DSBX_ActorEngineRegistry.Register(m_DsbxExpEngine);
	}

	override void OnUpdate(float timeslice)
	{
		super.OnUpdate(timeslice);
		if (m_DsbxExpEngine)
		{
			m_DsbxExpEngine.Tick(timeslice);
		}
	}
}
#endif
