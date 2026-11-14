modded class MissionServer
{
	ref DSBX_QA_Probe m_DsbxQaProbe;

	override void OnMissionStart()
	{
		super.OnMissionStart();
		m_DsbxQaProbe = new DSBX_QA_Probe("server");
	}

	override void OnUpdate(float timeslice)
	{
		super.OnUpdate(timeslice);
		if (m_DsbxQaProbe)
		{
			m_DsbxQaProbe.Tick();
		}
	}
}

modded class MissionGameplay
{
	ref DSBX_QA_Probe m_DsbxQaProbe;

	override void OnMissionStart()
	{
		super.OnMissionStart();
		m_DsbxQaProbe = new DSBX_QA_Probe("client");
	}

	override void OnUpdate(float timeslice)
	{
		super.OnUpdate(timeslice);
		if (m_DsbxQaProbe)
		{
			m_DsbxQaProbe.Tick();
		}
	}
}
