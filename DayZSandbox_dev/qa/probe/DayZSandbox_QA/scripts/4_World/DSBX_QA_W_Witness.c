// DSBX_QA_W_Witness.c — cobertura 4_World del testigo de creacion (el gancho y el bufer estan en
// 3_Game/DSBX_QA_G_Witness.c: DSBX_QA_Witness y modded class EntityAI). Aqui solo van los modded class de las clases
// vanilla de 4_world, que es su modulo (un modded class tiene que estar en el mismo modulo que la clase original).

// Cobertura de las clases vanilla cuyo override de EEInit NO llama a super.EEInit() (cortan la cadena y el gancho de
// EntityAI no las ve). Lista sacada con grep de los scripts vanilla (P:\scripts: 4_world/classes/contaminatedarea/
// contaminatedarea_local.c:30, 4_world/entities/woodbase/christmastree.c:16, 4_world/entities/creatures/animals/
// animalbase.c:153, 4_world/entities/creatures/infected/zombiemalebase.c:321). Cada clase repite la misma guarda de bool.
// Los dos ultimos solo existen en #ifndef SERVER / #ifndef NO_GUI en vanilla: en servidor no cortan la cadena y ya los ve
// el gancho de EntityAI (duplicarlo daria dos capturas).
// LIMITACION CONOCIDA: las clases de mods de terceros con el mismo patron (EEInit sin super.EEInit()) no se ven; el
// testigo solo garantiza lo vanilla. test_probe_ext_f2.py falla si aparece en vanilla una clase asi sin cubrir.
modded class ContaminatedArea_Local
{
	override void EEInit()
	{
		super.EEInit();
		if (!DSBX_QA_Witness.s_On)
			return;
		DSBX_QA_Witness.Capture(this);
	}
}

modded class ChristmasTree
{
	override void EEInit()
	{
		super.EEInit();
		if (!DSBX_QA_Witness.s_On)
			return;
		DSBX_QA_Witness.Capture(this);
	}
}

#ifndef SERVER
#ifndef NO_GUI
modded class Animal_CapraHircus_Spooky
{
	override void EEInit()
	{
		super.EEInit();
		if (!DSBX_QA_Witness.s_On)
			return;
		DSBX_QA_Witness.Capture(this);
	}
}

modded class ZmbM_Mummy
{
	override void EEInit()
	{
		super.EEInit();
		if (!DSBX_QA_Witness.s_On)
			return;
		DSBX_QA_Witness.Capture(this);
	}
}
#endif
#endif
