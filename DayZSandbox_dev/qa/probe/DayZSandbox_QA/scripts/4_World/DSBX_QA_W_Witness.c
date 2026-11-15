// DSBX_QA_W_Witness.c — creation witness hook (per_witness_start, extensiones de la sonda para F2).
// EntityAI es una clase del MOTOR y no se puede modar en ningun modulo ("Engine class 'EntityAI' cannot be modded"):
// el testigo se engancha en las RAICES DE SCRIPT moddables que derivan de EntityAI, todas de 4_world (el modulo de este
// fichero; un modded class tiene que estar en el mismo modulo que su clase original):
//   ItemBase       4_world/entities/itembase.c:23         (items, contenedores, tiendas, barriles, ropa: InventoryItem -> ItemBase)
//   ZombieBase     4_world/entities/creatures/infected/zombiebase.c:1   (todos los infectados)
//   AnimalBase     4_world/entities/creatures/animals/animalbase.c:1    (todos los animales)
//   CarScript      4_world/entities/vehicles/carscript.c:94 (coches: Car -> CarScript)
//   BuildingBase   4_world/entities/game/super/building.c:8 (House y edificios/props estaticos: Building -> BuildingBase)
// Ninguna es ascendiente de otra, asi que una entidad pasa por un solo gancho. Cada override: super.EEInit() primero,
// despues la guarda del bool estatico (apagado cuesta un bool) y Capture(this). Solo el servidor lo enciende: el unico
// que llama a Enable es DSBX_QA_X_Persist.HandleWitnessStart, que solo existe en el peer con role == "server".
// 5_Mission ve a 4_World: el trabajo "per_witness" de DSBX_QA_X_Persist lo enciende, lo vacia y escribe las filas.
//
// NO CUBIERTO (limitacion del contrato): lo que no deriva de esas raices no se ve: jugadores (ManBase), barcos y
// helicopteros (BoatScript, Helicopter), edificios que derivan directo de Building (AnniversaryMusicSource, ...),
// AdvancedCommunication, ScriptedEntity, EffecterBase y las clases de mods de terceros.
// net_id: en EEInit el motor aun no lo ha asignado (0:0); por eso la fila sample_idx 0 se emite en el primer tick de
// servidor con el net_id y el parent_net_id leidos entonces (posicion, orientacion, tick_ms y frame, los de EEInit).
// ai_agent_b: depende de que la entidad se cree con ECE_INITAI. per_spawn_raw foreign_ground crea sin IA y una criatura
// asi sale con ai_agent_b = 0 (medido en partida: la gallina).
//
// API verificada en P:\scripts:
//   EntityAI.EEInit()                   3_game/entities/entityai.c:905
//   Object.GetPosition()                3_game/entities/object.c:287
//   Object.GetOrientation()             3_game/entities/object.c:305
//   Object.GetNetworkID(low, high)      3_game/entities/object.c:819
//   EntityAI.GetHierarchyParent()       3_game/entities/entityai.c:885
//   DayZCreatureAI.GetAIAgent()         3_game/entities/dayzanimal.c:193
//   CGame.GetTickTime() (segundos)      3_game/global/game.c:914

class DSBX_QA_WitnessCapture : Managed
{
	Object m_Ent;
	string m_ClassName;
	string m_NetId;
	string m_ParentNetId;
	float m_PosX;
	float m_PosY;
	float m_PosZ;
	float m_YawDeg;
	float m_TickMs;
	int m_Frame;
	int m_AiAgentB;

	void DSBX_QA_WitnessCapture()
	{
		m_Ent = null;
		m_ClassName = "";
		m_NetId = "0:0";
		m_ParentNetId = "";
		m_PosX = 0.0;
		m_PosY = 0.0;
		m_PosZ = 0.0;
		m_YawDeg = 0.0;
		m_TickMs = 0.0;
		m_Frame = 0;
		m_AiAgentB = 0;
	}
}

class DSBX_QA_Witness
{
	// Una captura por entidad: con 4097 entradas el trabajo ya se pasa de max_rows (4096) al vaciarse y acaba
	// failed/rows_cap por el JobMgr; el bufer nunca crece sin tope y no se trunca en silencio.
	static const int BUFFER_MAX = 4097;

	static bool s_On = false;
	static float s_CenterX = 0.0;
	static float s_CenterZ = 0.0;
	static float s_Radius = 0.0;
	static float s_EndTickMs = 0.0;
	static int s_Frame = 0;
	static ref array<ref DSBX_QA_WitnessCapture> s_Buf;

	static void Enable(float centerX, float centerZ, float radius, float endTickMs, int frame)
	{
		if (!s_Buf)
		{
			s_Buf = new array<ref DSBX_QA_WitnessCapture>();
		}
		s_Buf.Clear();
		s_CenterX = centerX;
		s_CenterZ = centerZ;
		s_Radius = radius;
		s_EndTickMs = endTickMs;
		s_Frame = frame;
		s_On = true;
	}

	static void Disable()
	{
		s_On = false;
		if (s_Buf)
		{
			s_Buf.Clear();
		}
	}

	static void Capture(EntityAI ent)
	{
		if (!ent || !s_Buf)
		{
			return;
		}
		if (s_Buf.Count() >= BUFFER_MAX)
		{
			return;
		}
		float nowMs = g_Game.GetTickTime() * 1000.0;
		if (nowMs > s_EndTickMs)
		{
			return;
		}
		vector pos = ent.GetPosition();
		float dx = pos[0] - s_CenterX;
		float dz = pos[2] - s_CenterZ;
		if ((dx * dx + dz * dz) > (s_Radius * s_Radius))
		{
			return;
		}
		vector ori = ent.GetOrientation();
		int low = 0;
		int high = 0;
		ent.GetNetworkID(low, high);

		DSBX_QA_WitnessCapture cap = new DSBX_QA_WitnessCapture();
		cap.m_Ent = ent;
		cap.m_ClassName = ent.GetType();
		cap.m_NetId = high.ToString() + ":" + low.ToString();
		EntityAI parent = ent.GetHierarchyParent();
		if (parent)
		{
			int pLow = 0;
			int pHigh = 0;
			parent.GetNetworkID(pLow, pHigh);
			cap.m_ParentNetId = pHigh.ToString() + ":" + pLow.ToString();
		}
		cap.m_PosX = pos[0];
		cap.m_PosY = pos[1];
		cap.m_PosZ = pos[2];
		cap.m_YawDeg = ori[0];
		cap.m_TickMs = nowMs;
		cap.m_Frame = s_Frame;
		DayZCreatureAI creature = DayZCreatureAI.Cast(ent);
		if (creature && creature.GetAIAgent() != null)
		{
			cap.m_AiAgentB = 1;
		}
		s_Buf.Insert(cap);
	}
}

modded class ItemBase
{
	override void EEInit()
	{
		super.EEInit();
		if (!DSBX_QA_Witness.s_On)
			return;
		DSBX_QA_Witness.Capture(this);
	}
}

modded class ZombieBase
{
	override void EEInit()
	{
		super.EEInit();
		if (!DSBX_QA_Witness.s_On)
			return;
		DSBX_QA_Witness.Capture(this);
	}
}

modded class AnimalBase
{
	override void EEInit()
	{
		super.EEInit();
		if (!DSBX_QA_Witness.s_On)
			return;
		DSBX_QA_Witness.Capture(this);
	}
}

modded class CarScript
{
	override void EEInit()
	{
		super.EEInit();
		if (!DSBX_QA_Witness.s_On)
			return;
		DSBX_QA_Witness.Capture(this);
	}
}

modded class BuildingBase
{
	override void EEInit()
	{
		super.EEInit();
		if (!DSBX_QA_Witness.s_On)
			return;
		DSBX_QA_Witness.Capture(this);
	}
}

// Cobertura de las clases vanilla cuyo override de EEInit NO llama a super.EEInit() (cortan la cadena y el gancho de
// EntityAI no las ve). Lista sacada con grep de los scripts vanilla (P:\scripts: 4_world/classes/contaminatedarea/
// contaminatedarea_local.c:30, 4_world/entities/woodbase/christmastree.c:16, 4_world/entities/creatures/animals/
// animalbase.c:153, 4_world/entities/creatures/infected/zombiemalebase.c:321). Cada clase repite la misma guarda de bool. Las cuatro derivan de una raiz enganchada (House/BuildingBase,
// Animal_CapraHircus/AnimalBase, ZombieMaleBase/ZombieBase) y su override NO llama a super: la raiz no las ve y
// no hay doble captura (el modded class de cada una llama a super.EEInit(), que es el override de vanilla, y captura una vez).
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
