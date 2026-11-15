// Registra el motor de actores de Expansion en el núcleo, tras super.OnMissionStart() (que crea la sonda).
#ifdef EXPANSIONMODAI
modded class MissionServer
{
	override void OnMissionStart()
	{
		super.OnMissionStart();
		DSBX_QA_ActorRegistry.Register(new DSBX_QA_ExpansionBackend(), DSBX_QA_EXP_STAMP);
	}
}
#endif
