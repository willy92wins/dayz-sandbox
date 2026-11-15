// DSBX_QA_W_Witness.c — creation witness hook (per_witness_start, extensiones de la sonda para F2).
// 4_World no ve a 5_Mission, pero 5_Mission si ve a 4_World: este fichero solo guarda un bufer y un bool estatico;
// el trabajo "per_witness" de DSBX_QA_X_Persist (5_Mission) lo enciende, lo vacia y escribe las filas.
// Apagado (por defecto) el gancho de EEInit cuesta comprobar un static bool. Solo el servidor lo enciende: el unico
// que llama a Enable es DSBX_QA_X_Persist.HandleWitnessStart, que solo existe en el peer con role == "server".
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

modded class EntityAI
{
	override void EEInit()
	{
		super.EEInit();
		if (!DSBX_QA_Witness.s_On)
			return;
		DSBX_QA_Witness.Capture(this);
	}
}
