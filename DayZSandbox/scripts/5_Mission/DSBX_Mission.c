modded class MissionServer
{
	protected ref DSBX_World m_DsbxWorld;
	protected ref DSBX_Peer m_DsbxPeer;

	override void OnMissionStart()
	{
		super.OnMissionStart();
		m_DsbxWorld = new DSBX_World();
		m_DsbxWorld.InitServer();
		m_DsbxPeer = new DSBX_Peer("server", m_DsbxWorld);
	}

	override void OnMissionFinish()
	{
		if (m_DsbxPeer)
		{
			m_DsbxPeer.Shutdown();
			m_DsbxPeer = null;
		}
		m_DsbxWorld = null;
		super.OnMissionFinish();
	}

	override void OnUpdate(float timeslice)
	{
		super.OnUpdate(timeslice);
		if (m_DsbxPeer)
		{
			m_DsbxPeer.Tick(timeslice);
		}
	}

	override void InvokeOnConnect(PlayerBase player, PlayerIdentity identity)
	{
		super.InvokeOnConnect(player, identity);
		if (m_DsbxPeer && identity)
		{
			m_DsbxPeer.SendEpochToIdentity(identity);
		}
	}
}

modded class MissionGameplay
{
	protected ref DSBX_Peer m_DsbxPeer;

	override void OnMissionStart()
	{
		super.OnMissionStart();
		DSBX_CamEngineRegistry.Register(new DSBX_CamClient());
		m_DsbxPeer = new DSBX_Peer("client", null);
	}

	override void OnMissionFinish()
	{
		DSBX_CamEngineRegistry.Get().Stop();
		if (m_DsbxPeer)
		{
			m_DsbxPeer.Shutdown();
			m_DsbxPeer = null;
		}
		super.OnMissionFinish();
	}

	override void OnUpdate(float timeslice)
	{
		super.OnUpdate(timeslice);
		DSBX_CamEngineRegistry.Get().Tick(timeslice);
		if (m_DsbxPeer)
		{
			m_DsbxPeer.Tick(timeslice);
		}
	}
}
