// S-track·1 client probe. One hook writes the camera per run.
// Frame index advances only from MissionGameplay.OnUpdate.

// Brief v1.1 A (decision 2026-11-10 21:07Z): H-b = EOnPostFrame of the local
// player (vanilla sets POSTFRAME in playerbase.c:366 and overrides it at
// :4627). Own client entities created with ECE_LOCAL (House, local ItemBase)
// never received FRAME or POSTFRAME, and CfgVehicles has no ScriptedEntity.
modded class PlayerBase
{
	override void EOnPostFrame(IEntity other, int extra)
	{
		super.EOnPostFrame(other, extra);
		if (GetGame() && GetGame().GetPlayer() == this)
		{
			STRACK_Session.PostFrame();
		}
	}

	override void OnRPC(PlayerIdentity sender, int rpc_type, ParamsReadContext ctx)
	{
		int netLow;
		int netHigh;
		int ackTramo;
		int ackFin;
		super.OnRPC(sender, rpc_type, ctx);
		if (rpc_type == STRACK_RPC_POT_ACK)
		{
			ackTramo = 0;
			ackFin = 0;
			if (!ctx.Read(ackTramo))
			{
				Print("[STRACK] suave parada ACK lectura incompleta");
				return;
			}
			if (!ctx.Read(ackFin))
			{
				Print("[STRACK] suave parada ACK lectura incompleta");
				return;
			}
			STRACK_Move.NoteFrozenAck(ackTramo, ackFin);
			return;
		}
		if (rpc_type != STRACK_RPC_POT)
		{
			return;
		}
		netLow = 0;
		netHigh = 0;
		if (!ctx.Read(netLow))
		{
			Print("[STRACK] suave lata RPC lectura incompleta");
			return;
		}
		if (!ctx.Read(netHigh))
		{
			Print("[STRACK] suave lata RPC lectura incompleta");
			return;
		}
		STRACK_Session.SetPotId(netLow, netHigh);
	}
};

class STRACK_Session
{
	static ref STRACK_Session s_Me;

	protected bool m_ArgsReady;
	protected bool m_RunOn;
	protected bool m_Armed;
	protected bool m_Done;
	protected bool m_Self;
	protected bool m_HasRaw;
	protected bool m_FiltOn;
	protected bool m_Attached;
	protected bool m_BoneChecked;
	protected bool m_RelOk;
	protected bool m_LoggedDup;
	protected bool m_HoldLogged;
	protected string m_Caso;
	protected string m_Hook;
	protected string m_Inject;
	protected string m_Run;
	protected string m_Shot;
	protected int m_Frame;
	protected int m_Shots;
	protected int m_Samples;
	protected int m_Bone;
	protected int m_HbFrame;
	protected int m_HbInv;
	protected bool m_HbOpen;
	protected float m_Dt;
	protected float m_T0;
	protected float m_Now;
	protected float m_Yaw;
	protected float m_Fov;
	protected vector m_FixedPos;
	protected vector m_CalibAim;
	protected vector m_Raw[4];
	protected vector m_Prev[4];
	protected vector m_Filt[4];
	protected vector m_Written[4];
	protected vector m_Rel[4];
	protected FileHandle m_File;
	protected bool m_FileOpen;
	// Positions are written relative to a whole-metre origin fixed at arming:
	// float.ToString keeps ~6 significant digits, i.e. 1 cm at x=8400 m.
	protected vector m_Origin;
	// Orquestador 2026-11-11: armar solo tras STRACK_ARM_WAIT_S con el arma en manos, para que el
	// cliente (a menudo sin foco) termine de cargar texturas. -strack_wait=<s> lo cambia.
	protected float m_HandsSince;
	protected float m_ArmWait;
	protected Camera m_Cam;
	protected EntityAI m_Parent;
	protected int m_FpsCap;
	protected bool m_PfStarted;
	protected bool m_PfDone;
	protected float m_PfT0;
	protected float m_PfP50;
	protected float m_PfP95;
	protected ref array<float> m_PfDts;
	protected int m_CaseTick;
	protected int m_Tramo;
	protected float m_SmoothS;
	protected int m_GiroSuave;
	protected int m_PrevGiroSuave;
	protected bool m_LataOk;
	protected vector m_LataPos;
	protected vector m_CamRaw[4];
	protected float m_RawQ[4];
	protected float m_WrittenQ[4];
	protected bool m_QuatDotPending;
	protected float m_QuatDot;
	protected float m_SuaveBaseRot;
	protected bool m_SuaveBaseDone;
	protected EntityAI m_Lata;
	protected int m_ScanTick;
	protected ref array<Object> m_ScanObj;
	protected ref array<CargoBase> m_ScanCargo;
	protected int m_SpineBone;
	protected bool m_SpineChecked;
	protected bool m_RelMiraOk;
	protected vector m_RelMira[4];
	protected string m_MiraPoint;
	protected bool m_MiraPointLogged;
	protected bool m_MiraOk;
	protected bool m_LataReady;
	protected bool m_LataWaiting;
	protected float m_LataWaitT0;
	protected bool m_Tramo4Req;
	protected bool m_Tramo4Ack;
	protected float m_Tramo4ReqT0;
	protected float m_Tramo4T0;
	protected string m_FrozenRopa;
	protected int m_FrozenGiro;
	protected int m_FrozenSeg;
	protected static int s_PotLow;
	protected static int s_PotHigh;
	protected static bool s_PotIdOk;
	protected ref array<int> m_Ok;
	protected ref array<float> m_Px;
	protected ref array<float> m_Py;
	protected ref array<float> m_Pz;

	static void TickStatic(float dt)
	{
		if (!s_Me)
		{
			s_Me = new STRACK_Session();
		}
		s_Me.Tick(dt);
	}

	static void PostFrame()
	{
		if (s_Me)
		{
			s_Me.OnPostFrame();
		}
	}

	static void SetPotId(int netLow, int netHigh)
	{
		s_PotLow = netLow;
		s_PotHigh = netHigh;
		s_PotIdOk = true;
		Print("[STRACK] suave lata netid=" + netHigh.ToString() + ":" + netLow.ToString());
	}

	void STRACK_Session()
	{
		int i;
		m_Ok = new array<int>();
		m_Px = new array<float>();
		m_Py = new array<float>();
		m_Pz = new array<float>();
		m_PfDts = new array<float>();
		m_ScanObj = new array<Object>();
		m_ScanCargo = new array<CargoBase>();
		i = 0;
		while (i < 18)
		{
			m_Ok.Insert(0);
			m_Px.Insert(0);
			m_Py.Insert(0);
			m_Pz.Insert(0);
			i = i + 1;
		}
		m_Fov = 1.0471976;
		m_FrozenRopa = "";
		m_Frame = -1;
		m_Inject = "none";
		m_Hook = "";
		m_Caso = "";
		m_Shot = "";
		m_Bone = -1;
		m_HbFrame = -1;
		m_HandsSince = -1.0;
		m_ArmWait = 60.0;
		m_FpsCap = 60;
		m_Tramo = 1;
		m_SpineBone = -1;
		m_MiraPoint = "";
	}

	static bool Running()
	{
		if (!s_Me)
		{
			return false;
		}
		return s_Me.m_RunOn && !s_Me.m_Done;
	}

	protected bool IsSuave()
	{
		if (m_Caso == "suave30" || m_Caso == "suave60" || m_Caso == "suave144")
		{
			return true;
		}
		return false;
	}

	protected int CurrentGiro()
	{
		if (IsSuave())
		{
			return m_GiroSuave;
		}
		if (m_Self)
		{
			return STRACK_Move.Giro();
		}
		return 0;
	}

	protected void Tick(float dt)
	{
		PlayerBase player;
		int tramoSend;
		if (m_Done)
		{
			return;
		}
		if (!GetGame())
		{
			return;
		}
		if (!m_ArgsReady)
		{
			ReadArgs();
			m_ArgsReady = true;
			if (!m_RunOn)
			{
				if (m_Caso == "")
				{
					Print("[STRACK] sin -strack ni strack_args.txt; la sonda no arranca");
				}
				m_Done = true;
				return;
			}
		}
		if (!m_RunOn)
		{
			return;
		}
		STRACK_Move.FlushPending();
		m_CaseTick = m_CaseTick + 1;
		if ((m_CaseTick % 60) == 1 && !STRACK_Move.HasPending())
		{
			tramoSend = 0;
			if (IsSuave())
			{
				tramoSend = m_Tramo;
				if (m_Tramo4Req)
				{
					tramoSend = 4;
				}
			}
			STRACK_Move.SendCaseState(m_Caso, tramoSend, false);
		}
		if (!m_Armed)
		{
			if (!TryArm(dt))
			{
				return;
			}
		}
		FlushHb();
		if (ShouldStop())
		{
			Finish("stop");
			return;
		}
		if (IsSuave() && !SuaveTramo4Gate())
		{
			return;
		}
		m_Dt = dt;
		m_Frame = m_Frame + 1;
		player = PlayerBase.Cast(GetGame().GetPlayer());
		if (m_Hook == "Ha" || m_Hook == "Hc")
		{
			Capture(true);
		}
		if (m_Caso == "calib" && m_Shots >= 200)
		{
			Finish("calib");
		}
		if (IsSuave() && m_Armed && m_Tramo4Ack && (GetGame().GetTickTime() - m_Tramo4T0) >= 8.5)
		{
			Finish("suave");
		}
	}

	protected void OnPostFrame()
	{
		if (m_Done || !m_Armed || m_Hook != "Hb")
		{
			return;
		}
		if (m_HbOpen && m_HbFrame == m_Frame)
		{
			m_HbInv = m_HbInv + 1;
			if (!m_LoggedDup)
			{
				Print("[STRACK] H-b repite EOnPostFrame en el mismo frame");
				m_LoggedDup = true;
			}
			return;
		}
		Capture(false);
		m_HbFrame = m_Frame;
		m_HbInv = 1;
		m_HbOpen = true;
		if (m_Caso == "calib" && m_Shots >= 200)
		{
			Finish("calib");
		}
	}

	protected void ReadArgs()
	{
		string v;
		bool fromCli;
		v = "";
		fromCli = GetCLIParam("strack", v);
		if (fromCli)
		{
			m_Caso = v;
			m_Hook = "Ha";
			m_Inject = "none";
			if (GetCLIParam("strack_hook", v))
			{
				m_Hook = v;
			}
			if (GetCLIParam("strack_inject", v))
			{
				m_Inject = v;
			}
			if (GetCLIParam("strack_move", v))
			{
				if (v == "self")
				{
					m_Self = true;
				}
			}
			if (GetCLIParam("strack_wait", v))
			{
				m_ArmWait = v.ToFloat();
			}
			if (GetCLIParam("strack_fps_cap", v))
			{
				m_FpsCap = v.ToInt();
			}
			Print("[STRACK] args CLI caso=" + m_Caso + " hook=" + m_Hook + " inject=" + m_Inject);
		}
		else
		{
			ReadFileArgs();
		}
		if (!AcceptArgs())
		{
			m_RunOn = false;
			return;
		}
		m_Run = m_Caso + "_" + m_Hook;
		if (m_Inject != "none")
		{
			m_Run = m_Run + "_" + m_Inject;
		}
		m_RunOn = true;
		if (m_Self)
		{
			Print("[STRACK] run=" + m_Run + " self=1");
		}
		else
		{
			Print("[STRACK] run=" + m_Run + " self=0");
		}
	}

	protected void ReadFileArgs()
	{
		FileHandle file;
		string line;
		string key;
		string val;
		int cut;
		file = OpenFile("$profile:strack/strack_args.txt", FileMode.READ);
		if (file == 0)
		{
			Print("[STRACK] no hay $profile:strack/strack_args.txt");
			return;
		}
		line = "";
		while (FGets(file, line) > 0)
		{
			line.Replace("\r", "");
			line.Replace("\n", "");
			cut = line.IndexOf("=");
			if (cut > 0)
			{
				key = line.Substring(0, cut);
				val = line.Substring(cut + 1, line.Length() - cut - 1);
				if (key == "strack")
				{
					m_Caso = val;
				}
				if (key == "strack_hook")
				{
					m_Hook = val;
				}
				if (key == "strack_inject")
				{
					m_Inject = val;
				}
				if (key == "strack_move" && val == "self")
				{
					m_Self = true;
				}
				if (key == "strack_wait")
				{
					m_ArmWait = val.ToFloat();
				}
				if (key == "strack_fps_cap")
				{
					m_FpsCap = val.ToInt();
				}
			}
		}
		CloseFile(file);
		if (m_Hook == "")
		{
			m_Hook = "Ha";
		}
		if (m_Inject == "")
		{
			m_Inject = "none";
		}
		Print("[STRACK] args fichero caso=" + m_Caso + " hook=" + m_Hook + " inject=" + m_Inject);
	}

	protected bool AcceptArgs()
	{
		bool casoOk;
		bool hookOk;
		bool suave;
		casoOk = false;
		if (m_Caso == "calib" || m_Caso == "mount0" || m_Caso == "mount03" || m_Caso == "lookat" || m_Caso == "follow")
		{
			casoOk = true;
		}
		if (m_Caso == "ropa" || m_Caso == "suave30" || m_Caso == "suave60" || m_Caso == "suave144")
		{
			casoOk = true;
		}
		if (!casoOk)
		{
			Print("[STRACK] caso no valido: " + m_Caso);
			return false;
		}
		hookOk = false;
		if (m_Hook == "Ha" || m_Hook == "Hb" || m_Hook == "Hc")
		{
			hookOk = true;
		}
		if (!hookOk)
		{
			Print("[STRACK] hook no valido: " + m_Hook);
			return false;
		}
		suave = IsSuave();
		if (suave)
		{
			if (m_Hook != "Hb")
			{
				Print("[STRACK] suave solo vale con Hb");
				return false;
			}
			if (m_Inject != "none" && m_Inject != "smooth03" && m_Inject != "quatlerp" && m_Inject != "longarc")
			{
				Print("[STRACK] inject no valido en suave: " + m_Inject);
				return false;
			}
			return true;
		}
		if (m_Inject != "none" && m_Inject != "delay1" && m_Inject != "roll")
		{
			Print("[STRACK] inject no valido: " + m_Inject);
			return false;
		}
		if (m_Hook == "Hc" && m_Caso != "mount0" && m_Caso != "ropa")
		{
			Print("[STRACK] H-c solo vale para mount0 y ropa");
			return false;
		}
		return true;
	}

	protected float Percentile(array<float> vals, float frac)
	{
		int n;
		int idx;
		n = vals.Count();
		if (n == 0)
		{
			return 0.0;
		}
		idx = (int)(frac * (n - 1));
		if (idx < 0)
		{
			idx = 0;
		}
		if (idx >= n)
		{
			idx = n - 1;
		}
		return vals.Get(idx);
	}

	protected void SortFloats(array<float> vals)
	{
		int i;
		int j;
		float tmp;
		i = 1;
		while (i < vals.Count())
		{
			j = i;
			while (j > 0 && vals.Get(j) < vals.Get(j - 1))
			{
				tmp = vals.Get(j);
				vals.Set(j, vals.Get(j - 1));
				vals.Set(j - 1, tmp);
				j = j - 1;
			}
			i = i + 1;
		}
	}

	protected void ResetPreflight()
	{
		if (!m_PfStarted || m_PfDone)
		{
			return;
		}
		m_PfStarted = false;
		m_PfT0 = 0.0;
		m_PfDts.Clear();
		Print("[STRACK] preflight reiniciado");
	}

	protected bool Preflight(float dt)
	{
		float now;
		float umbral;
		float capMs;
		FileHandle pf;
		FileHandle df;
		string body;
		now = GetGame().GetTickTime();
		if (!m_PfStarted)
		{
			m_PfStarted = true;
			m_PfT0 = now;
			m_PfDts.Clear();
			Print("[STRACK] preflight fps: midiendo 10 s");
			return false;
		}
		if (dt > 0.0)
		{
			m_PfDts.Insert(dt * 1000.0);
		}
		if ((now - m_PfT0) < 10.0)
		{
			return false;
		}
		SortFloats(m_PfDts);
		m_PfP50 = Percentile(m_PfDts, 0.5);
		m_PfP95 = Percentile(m_PfDts, 0.95);
		capMs = 18.0;
		if (m_FpsCap > 0)
		{
			capMs = 1.08 * 1000.0 / m_FpsCap;
		}
		umbral = capMs;
		if (umbral < 18.0)
		{
			umbral = 18.0;
		}
		if (m_PfP50 > umbral)
		{
			Print("[STRACK] preflight fps p50=" + STRACK_Math.N(m_PfP50) + " umbral=" + STRACK_Math.N(umbral) + " ok=0");
			if (!MakeDirectory("$profile:strack"))
			{
				Print("[STRACK] MakeDirectory strack fallo (puede existir)");
			}
			if (!MakeDirectory("$profile:strack/" + m_Run))
			{
				Print("[STRACK] MakeDirectory run fallo (puede existir)");
			}
			body = "{\"run\":\"" + m_Run + "\",\"ok\":false,\"causa\":\"fps\",\"dt_p50_ms\":" + STRACK_Math.N(m_PfP50) + ",\"umbral_ms\":" + STRACK_Math.N(umbral) + ",\"n\":" + m_PfDts.Count().ToString() + "}";
			df = OpenFile("$profile:strack/" + m_Run + "/done.json", FileMode.WRITE);
			if (df != 0)
			{
				FPrintln(df, body);
				CloseFile(df);
			}
			m_RunOn = false;
			m_Done = true;
			return false;
		}
		Print("[STRACK] preflight fps p50=" + STRACK_Math.N(m_PfP50) + " umbral=" + STRACK_Math.N(umbral) + " ok=1");
		if (!MakeDirectory("$profile:strack"))
		{
			Print("[STRACK] MakeDirectory strack fallo (puede existir)");
		}
		if (!MakeDirectory("$profile:strack/" + m_Run))
		{
			Print("[STRACK] MakeDirectory run fallo (puede existir)");
		}
		body = "{\"dt_p50_ms\":" + STRACK_Math.N(m_PfP50) + ",\"dt_p95_ms\":" + STRACK_Math.N(m_PfP95) + ",\"n\":" + m_PfDts.Count().ToString() + ",\"umbral_ms\":" + STRACK_Math.N(umbral) + "}";
		pf = OpenFile("$profile:strack/" + m_Run + "/preflight.json", FileMode.WRITE);
		if (pf != 0)
		{
			FPrintln(pf, body);
			CloseFile(pf);
		}
		m_PfDone = true;
		return true;
	}

	protected bool PotStopConfirmed()
	{
		if (!GetGame() || !GetGame().IsMultiplayer())
		{
			return STRACK_Move.ServerPotFrozen();
		}
		if (GetGame().IsServer())
		{
			// Listen-server / same process: the local statics already froze it.
			if (STRACK_Move.ServerPotFrozen())
			{
				return true;
			}
		}
		return STRACK_Move.FrozenAckReceived();
	}

	protected bool SuaveTramo4Gate()
	{
		float now;
		now = GetGame().GetTickTime();
		if (m_Tramo4Ack)
		{
			return true;
		}
		if (!m_Tramo4Req)
		{
			if ((now - m_T0) < 30.0)
			{
				return true;
			}
			m_Tramo4Req = true;
			m_Tramo4ReqT0 = now;
			STRACK_Move.ClearFrozenAck();
			STRACK_Move.SendCaseState(m_Caso, 4, false);
			Print("[STRACK] suave parada pedida; esperando confirmacion del servidor");
			return true;
		}
		STRACK_Move.FlushPending();
		if (PotStopConfirmed())
		{
			m_Tramo4Ack = true;
			m_Tramo4T0 = now;
			m_Tramo = 4;
			Print("[STRACK] suave tramo4 reloj arranca tras confirmacion");
			return true;
		}
		if ((now - m_Tramo4ReqT0) >= 3.0)
		{
			Print("[STRACK] suave parada no confirmada en 3 s");
			WriteFailDone("lata_no_para");
			return false;
		}
		return true;
	}

	protected void WriteFailDone(string causa)
	{
		string done;
		FileHandle doneFile;
		if (m_Done)
		{
			return;
		}
		m_Done = true;
		if (IsSuave())
		{
			STRACK_Move.SendCaseState(m_Caso, m_Tramo, true);
		}
		FlushHb();
		if (m_Attached && m_Parent && m_Cam)
		{
			m_Parent.RemoveChild(m_Cam, true);
		}
		if (m_Cam)
		{
			m_Cam.SetActive(false);
		}
		if (m_FileOpen)
		{
			CloseFile(m_File);
			m_FileOpen = false;
		}
		if (!MakeDirectory("$profile:strack"))
		{
			Print("[STRACK] MakeDirectory strack fallo (puede existir)");
		}
		if (!MakeDirectory("$profile:strack/" + m_Run))
		{
			Print("[STRACK] MakeDirectory run fallo (puede existir)");
		}
		done = "{\"run\":\"" + m_Run + "\",\"frames\":" + m_Samples.ToString() + ",\"shots\":" + m_Shots.ToString() + ",\"ok\":false,\"causa\":\"" + causa + "\"}";
		doneFile = OpenFile("$profile:strack/" + m_Run + "/done.json", FileMode.WRITE);
		if (doneFile != 0)
		{
			FPrintln(doneFile, done);
			CloseFile(doneFile);
		}
		else
		{
			Print("[STRACK] no se abre done.json");
		}
		m_RunOn = false;
		STRACK_Move.Stop();
		Print("[STRACK] fin fallo causa=" + causa);
	}

	protected bool TryArm(float dt)
	{
		PlayerBase player;
		HumanInventory inv;
		EntityAI weapon;
		EntityAI lata;
		Object created;
		vector pos;
		vector fwd;
		float heading;
		HumanInputController hic;
		player = PlayerBase.Cast(GetGame().GetPlayer());
		if (!player)
		{
			ResetPreflight();
			return false;
		}
		inv = player.GetHumanInventory();
		if (!inv)
		{
			ResetPreflight();
			return false;
		}
		weapon = inv.GetEntityInHands();
		if (!weapon)
		{
			m_HandsSince = -1.0;
			ResetPreflight();
			return false;
		}
		if (m_HandsSince < 0.0)
		{
			m_HandsSince = GetGame().GetTickTime();
			Print("[STRACK] arma en manos; espera de " + m_ArmWait.ToString() + " s antes de armar");
			return false;
		}
		if (GetGame().GetTickTime() - m_HandsSince < m_ArmWait)
		{
			return false;
		}
		if (!m_PfDone)
		{
			if (!Preflight(dt))
			{
				return false;
			}
		}
		if (IsSuave() && !m_LataReady)
		{
			// Resolve/validate the pot (network-id matched in FindLata) before
			// fixing m_T0, opening samples.jsonl or capturing (§16 / MAY).
			lata = FindLata(player);
			if (lata)
			{
				m_Lata = lata;
				m_LataOk = true;
				m_LataPos = lata.GetWorldPosition();
				m_LataReady = true;
				m_LataWaiting = false;
				Print("[STRACK] suave lata lista antes de armar pos=" + STRACK_Math.V(m_LataPos));
			}
			else
			{
				if (!m_LataWaiting)
				{
					m_LataWaiting = true;
					m_LataWaitT0 = GetGame().GetTickTime();
					Print("[STRACK] suave esperando lata (tope 10 s)");
				}
				if ((GetGame().GetTickTime() - m_LataWaitT0) >= 10.0)
				{
					Print("[STRACK] suave sin lata en 10 s");
					WriteFailDone("sin_lata");
				}
				return false;
			}
		}
		if (!MakeDirectory("$profile:strack"))
		{
			Print("[STRACK] MakeDirectory strack fallo (puede existir)");
		}
		if (!MakeDirectory("$profile:strack/" + m_Run))
		{
			Print("[STRACK] MakeDirectory run fallo (puede existir)");
		}
		m_File = OpenFile("$profile:strack/" + m_Run + "/samples.jsonl", FileMode.WRITE);
		if (m_File == 0)
		{
			Print("[STRACK] no se abre samples.jsonl");
			m_RunOn = false;
			m_Done = true;
			return false;
		}
		m_FileOpen = true;
		pos = player.GetPosition();
		fwd = Vector(0, 0, 1);
		hic = player.GetInputController();
		if (hic)
		{
			heading = hic.GetHeadingAngle();
			fwd = Vector(Math.Cos(heading + Math.PI_HALF), 0, Math.Sin(heading + Math.PI_HALF));
		}
		// Side view so usti/konec stay apart on screen. follow/mount do not use this.
		fwd = Vector(fwd[2], 0, -fwd[0]);
		// Brief v1.1 (hilo, 2026-11-11): lookat con la camara fija a 1,3 m del punto de giro
		// (a 4 m la boca y la recamara quedaban a ~40 px con f = 684 px; hacen falta >= 200 px).
		m_FixedPos = pos + fwd * 1.3 + Vector(0, 1.5, 0);
		m_CalibAim = pos + Vector(0, 1.5, 0);
		if (m_Caso == "calib")
		{
			m_FixedPos = pos + fwd * 3.0 + Vector(0, 1.6, 0);
		}
		created = GetGame().CreateObject("staticcamera", m_FixedPos, true);
		Class.CastTo(m_Cam, created);
		if (!m_Cam)
		{
			Print("[STRACK] CreateObject staticcamera devolvio null");
			m_RunOn = false;
			m_Done = true;
			return false;
		}
		m_Cam.SetNearPlane(0.02);
		m_Cam.SetFOV(m_Fov);
		m_Cam.SetActive(true);
		m_Origin = Vector(Math.Round(pos[0]), Math.Round(pos[1]), Math.Round(pos[2]));
		m_T0 = GetGame().GetTickTime();
		m_Armed = true;
		if (m_Self && !IsSuave())
		{
			STRACK_Move.Begin(m_Caso == "lookat");
		}
		if (IsSuave())
		{
			STRACK_Move.SendCaseState(m_Caso, 1, false);
		}
		Print("[STRACK] armado arma=" + weapon.GetType() + " fov=" + m_Fov.ToString());
		return true;
	}

	protected bool ShouldStop()
	{
		float elapsed;
		if (m_Caso == "calib")
		{
			return false;
		}
		if (FileExist("$profile:strack/" + m_Run + "/stop.txt"))
		{
			Print("[STRACK] stop.txt");
			return true;
		}
		elapsed = GetGame().GetTickTime() - m_T0;
		if (elapsed >= 90.0)
		{
			Print("[STRACK] tope 90 s");
			return true;
		}
		return false;
	}

	protected void Capture(bool writeNow)
	{
		PlayerBase player;
		EntityAI weapon;
		vector pose[4];
		bool wrote;
		m_Now = GetGame().GetTickTime();
		player = PlayerBase.Cast(GetGame().GetPlayer());
		weapon = null;
		if (player && player.GetHumanInventory())
		{
			weapon = player.GetHumanInventory().GetEntityInHands();
		}
		if (IsSuave() && player)
		{
			if (weapon)
			{
				FillReadings(player, weapon);
			}
			else
			{
				ClearAllReadings();
			}
			wrote = BuildPoseSuave(player, weapon, pose);
		}
		else if (weapon && player)
		{
			FillReadings(player, weapon);
			if (m_Caso == "ropa")
			{
				FillMiraReadings(player, weapon);
			}
			wrote = BuildPose(weapon, pose);
		}
		else
		{
			ClearAllReadings();
			wrote = false;
			if (!m_HoldLogged)
			{
				Print("[STRACK] sin arma en manos; la camara se queda");
				m_HoldLogged = true;
			}
		}
		if (!wrote)
		{
			STRACK_Math.Copy4(m_Written, pose);
		}
		m_FrozenGiro = CurrentGiro();
		m_FrozenSeg = STRACK_Move.Seg();
		if (m_Caso == "ropa")
		{
			m_FrozenRopa = RopaJson(player, weapon);
		}
		ApplyShot();
		if (writeNow)
		{
			WriteLine(1);
		}
	}

	protected void ClearAllReadings()
	{
		int i;
		m_MiraOk = false;
		i = 0;
		while (i < 18)
		{
			m_Ok.Set(i, 0);
			i = i + 1;
		}
	}

	protected void SetRead(int index, vector v)
	{
		m_Ok.Set(index, 1);
		m_Px.Set(index, v[0]);
		m_Py.Set(index, v[1]);
		m_Pz.Set(index, v[2]);
	}

	protected void FillReadings(PlayerBase player, EntityAI weapon)
	{
		int p;
		int base;
		string name;
		vector mp;
		vector rt[4];
		vector tm[4];
		bool hasMp;
		p = 0;
		while (p < 2)
		{
			name = "usti hlavne";
			if (p == 1)
			{
				name = "konec hlavne";
			}
			base = p * 6;
			hasMp = weapon.MemoryPointExists(name);
			mp = Vector(0, 0, 0);
			if (hasMp)
			{
				mp = weapon.GetMemoryPointPos(name);
				SetRead(base, weapon.ModelToWorld(mp));
			}
			else
			{
				m_Ok.Set(base, 0);
			}
			SetRead(base + 1, weapon.GetSelectionPositionWS(name));
			SetRead(base + 2, player.ModelToWorld(weapon.GetSelectionPositionMS(name)));
			FillBone(player, weapon, mp, hasMp, base + 3);
			weapon.GetRenderTransform(rt);
			if (hasMp)
			{
				SetRead(base + 4, STRACK_Math.MulPoint(rt, mp));
			}
			else
			{
				m_Ok.Set(base + 4, 0);
			}
			weapon.GetTransform(tm);
			tm[3] = weapon.GetWorldPosition();
			if (hasMp)
			{
				SetRead(base + 5, STRACK_Math.MulPoint(tm, mp));
			}
			else
			{
				m_Ok.Set(base + 5, 0);
			}
			p = p + 1;
		}
	}

	protected void FillBone(PlayerBase player, EntityAI weapon, vector mp, bool hasMp, int slot)
	{
		vector bone[4];
		vector wtm[4];
		vector inv[4];
		vector posed[4];
		if (!m_BoneChecked)
		{
			m_Bone = player.GetBoneIndexByName("RightHand_Dummy");
			m_BoneChecked = true;
			if (m_Bone == -1)
			{
				Print("[STRACK] RightHand_Dummy ausente (-1)");
			}
		}
		if (m_Bone == -1 || !hasMp)
		{
			m_Ok.Set(slot, 0);
			return;
		}
		if (!m_RelOk)
		{
			player.GetBoneTransformWS(m_Bone, bone);
			weapon.GetTransform(wtm);
			STRACK_Math.Copy4(bone, inv);
			Math3D.MatrixInverse4(inv);
			Math3D.MatrixMultiply4(inv, wtm, m_Rel);
			m_RelOk = true;
		}
		player.GetBoneTransformWS(m_Bone, bone);
		Math3D.MatrixMultiply4(bone, m_Rel, posed);
		SetRead(slot, STRACK_Math.MulPoint(posed, mp));
	}

	protected EntityAI FindByType(EntityAI parent, string typeName)
	{
		GameInventory inv;
		EntityAI att;
		int i;
		int count;
		if (!parent)
		{
			return null;
		}
		inv = parent.GetInventory();
		if (!inv)
		{
			return null;
		}
		count = inv.AttachmentCount();
		i = 0;
		while (i < count)
		{
			att = inv.GetAttachmentFromIndex(i);
			if (att && att.IsKindOf(typeName))
			{
				return att;
			}
			i = i + 1;
		}
		return null;
	}

	protected void FillMiraReadings(PlayerBase player, EntityAI weapon)
	{
		EntityAI mira;
		vector mp;
		vector rt[4];
		vector tm[4];
		bool hasMp;
		int base;
		base = 12;
		m_MiraOk = false;
		mira = FindByType(weapon, "ACOGOptic");
		if (!mira)
		{
			m_Ok.Set(base, 0);
			m_Ok.Set(base + 1, 0);
			m_Ok.Set(base + 2, 0);
			m_Ok.Set(base + 3, 0);
			m_Ok.Set(base + 4, 0);
			m_Ok.Set(base + 5, 0);
			return;
		}
		if (!m_MiraPointLogged)
		{
			m_MiraPoint = "";
			if (mira.MemoryPointExists("eyeScope"))
			{
				m_MiraPoint = "eyeScope";
			}
			else if (mira.MemoryPointExists("eyeIronsights"))
			{
				m_MiraPoint = "eyeIronsights";
			}
			else if (mira.MemoryPointExists("cameraDir"))
			{
				m_MiraPoint = "cameraDir";
			}
			else if (mira.MemoryPointExists("cameraDirIronsights"))
			{
				m_MiraPoint = "cameraDirIronsights";
			}
			if (m_MiraPoint == "")
			{
				Print("[STRACK] ropa punto mira=ninguno");
			}
			else
			{
				Print("[STRACK] ropa punto mira=" + m_MiraPoint);
			}
			m_MiraPointLogged = true;
		}
		if (m_MiraPoint == "")
		{
			m_Ok.Set(base, 0);
			m_Ok.Set(base + 1, 0);
			m_Ok.Set(base + 2, 0);
			m_Ok.Set(base + 3, 0);
			m_Ok.Set(base + 4, 0);
			m_Ok.Set(base + 5, 0);
			return;
		}
		hasMp = mira.MemoryPointExists(m_MiraPoint);
		mp = Vector(0, 0, 0);
		if (hasMp)
		{
			mp = mira.GetMemoryPointPos(m_MiraPoint);
			m_MiraOk = true;
		}
		if (hasMp)
		{
			SetRead(base, mira.ModelToWorld(mp));
		}
		else
		{
			m_Ok.Set(base, 0);
		}
		SetRead(base + 1, mira.GetSelectionPositionWS(m_MiraPoint));
		SetRead(base + 2, player.ModelToWorld(mira.GetSelectionPositionMS(m_MiraPoint)));
		FillBoneMira(player, mira, mp, hasMp, base + 3);
		mira.GetRenderTransform(rt);
		if (hasMp)
		{
			SetRead(base + 4, STRACK_Math.MulPoint(rt, mp));
		}
		else
		{
			m_Ok.Set(base + 4, 0);
		}
		mira.GetTransform(tm);
		tm[3] = mira.GetWorldPosition();
		if (hasMp)
		{
			SetRead(base + 5, STRACK_Math.MulPoint(tm, mp));
		}
		else
		{
			m_Ok.Set(base + 5, 0);
		}
	}

	protected void FillBoneMira(PlayerBase player, EntityAI mira, vector mp, bool hasMp, int slot)
	{
		vector bone[4];
		vector wtm[4];
		vector inv[4];
		vector posed[4];
		if (!m_BoneChecked)
		{
			m_Bone = player.GetBoneIndexByName("RightHand_Dummy");
			m_BoneChecked = true;
			if (m_Bone == -1)
			{
				Print("[STRACK] RightHand_Dummy ausente (-1)");
			}
		}
		if (m_Bone == -1 || !hasMp)
		{
			m_Ok.Set(slot, 0);
			return;
		}
		if (!m_RelMiraOk)
		{
			player.GetBoneTransformWS(m_Bone, bone);
			mira.GetTransform(wtm);
			STRACK_Math.Copy4(bone, inv);
			Math3D.MatrixInverse4(inv);
			Math3D.MatrixMultiply4(inv, wtm, m_RelMira);
			m_RelMiraOk = true;
		}
		player.GetBoneTransformWS(m_Bone, bone);
		Math3D.MatrixMultiply4(bone, m_RelMira, posed);
		SetRead(slot, STRACK_Math.MulPoint(posed, mp));
	}

	protected bool Anchor(EntityAI weapon, string name, out vector pos, out vector axes[4])
	{
		vector mp;
		if (!weapon.MemoryPointExists(name))
		{
			return false;
		}
		weapon.GetTransform(axes);
		mp = weapon.GetMemoryPointPos(name);
		pos = weapon.ModelToWorld(mp);
		return true;
	}

	protected bool BuildPose(EntityAI weapon, out vector written[4])
	{
		vector axes[4];
		vector usti;
		vector konec;
		vector raw[4];
		vector used[4];
		vector looked[4];
		vector filtered[4];
		vector rolled[4];
		bool haveUsti;
		bool haveKonec;
		float alpha;
		m_Yaw = 0.0;
		haveUsti = Anchor(weapon, "usti hlavne", usti, axes);
		haveKonec = Anchor(weapon, "konec hlavne", konec, axes);
		if (m_Caso == "calib")
		{
			STRACK_Math.Look(m_FixedPos, m_CalibAim, Vector(0, 1, 0), looked);
			if (CalibBit(m_Frame))
			{
				m_Yaw = 10.0;
			}
			STRACK_Math.YawRight(looked, m_Yaw, raw);
		}
		else if (m_Caso == "lookat")
		{
			if (!haveUsti)
			{
				return false;
			}
			STRACK_Math.Look(m_FixedPos, usti, Vector(0, 1, 0), raw);
		}
		else if (m_Caso == "follow")
		{
			if (!haveUsti)
			{
				return false;
			}
			BuildFollow(usti, axes, raw);
		}
		else
		{
			if (!haveUsti || !haveKonec)
			{
				return false;
			}
			BuildMount(usti, konec, axes, raw);
		}
		if (m_Inject == "delay1" && m_HasRaw)
		{
			STRACK_Math.Copy4(m_Prev, used);
		}
		else
		{
			STRACK_Math.Copy4(raw, used);
		}
		if (m_Caso == "mount03")
		{
			alpha = 1.0;
			if (m_FiltOn && m_Dt > 0.0)
			{
				alpha = 1.0 - STRACK_Math.Exp(-m_Dt / 0.3);
			}
			if (!m_FiltOn)
			{
				STRACK_Math.Copy4(used, m_Filt);
				m_FiltOn = true;
			}
			else
			{
				STRACK_Math.Slerp(m_Filt, used, alpha, filtered);
				filtered[3] = m_Filt[3] + (used[3] - m_Filt[3]) * alpha;
				STRACK_Math.Copy4(filtered, m_Filt);
			}
			STRACK_Math.Copy4(m_Filt, used);
		}
		if (m_Inject == "roll")
		{
			STRACK_Math.RollOptic(used, 1.0, rolled);
			STRACK_Math.Copy4(rolled, used);
		}
		STRACK_Math.Copy4(raw, m_Prev);
		m_HasRaw = true;
		STRACK_Math.Copy4(used, m_Written);
		STRACK_Math.Copy4(used, written);
		STRACK_Math.MatQuat(m_Written, m_WrittenQ);
		STRACK_Math.Copy4(raw, m_CamRaw);
		STRACK_Math.MatQuat(m_CamRaw, m_RawQ);
		WriteCamera(weapon, used);
		return true;
	}

	protected EntityAI FindLata(PlayerBase player)
	{
		int i;
		Object obj;
		EntityAI ent;
		int candLow;
		int candHigh;
		candLow = 0;
		candHigh = 0;
		if (!s_PotIdOk)
		{
			return null;
		}
		if (m_Lata && m_Lata.IsKindOf("Pot"))
		{
			m_Lata.GetNetworkID(candLow, candHigh);
			if (candLow == s_PotLow && candHigh == s_PotHigh)
			{
				return m_Lata;
			}
			m_Lata = null;
		}
		m_ScanObj.Clear();
		m_ScanCargo.Clear();
		GetGame().GetObjectsAtPosition(player.GetPosition(), 15.0, m_ScanObj, m_ScanCargo);
		i = 0;
		while (i < m_ScanObj.Count())
		{
			obj = m_ScanObj.Get(i);
			ent = EntityAI.Cast(obj);
			if (ent && ent.IsKindOf("Pot") && !ent.GetHierarchyParent())
			{
				candLow = 0;
				candHigh = 0;
				ent.GetNetworkID(candLow, candHigh);
				if (candLow == s_PotLow && candHigh == s_PotHigh)
				{
					m_Lata = ent;
					return m_Lata;
				}
			}
			i = i + 1;
		}
		return null;
	}

	protected bool BuildPoseSuave(PlayerBase player, EntityAI weapon, out vector written[4])
	{
		EntityAI lata;
		vector lataTm[4];
		vector axesRot[4];
		vector raw[4];
		vector rawYaw[4];
		vector used[4];
		vector filtered[4];
		float elapsed;
		float t4;
		float yawOff;
		float alpha;
		int mode;
		float qa[4];
		float qb[4];
		float cand[8];
		int ci;
		float bestDot;
		float dTry;
		vector tryMat[4];
		vector tryAxes[4];
		int prevTramo;
		lata = null;
		m_ScanTick = m_ScanTick + 1;
		if (!m_Lata || (m_ScanTick % 30) == 0)
		{
			lata = FindLata(player);
		}
		else
		{
			lata = m_Lata;
		}
		if (!lata)
		{
			m_LataOk = false;
			return false;
		}
		m_LataOk = true;
		m_LataPos = lata.GetWorldPosition();
		lata.GetTransform(lataTm);
		prevTramo = m_Tramo;
		elapsed = m_Now - m_T0;
		if (elapsed < 10.0)
		{
			m_Tramo = 1;
			m_SmoothS = 0.0;
		}
		else if (elapsed < 20.0)
		{
			m_Tramo = 2;
			m_SmoothS = 0.3;
		}
		else if (elapsed < 30.0)
		{
			m_Tramo = 3;
			m_SmoothS = 0.8;
		}
		else if (m_Tramo4Ack)
		{
			m_Tramo = 4;
			m_SmoothS = 0.3;
		}
		else
		{
			// Tramo 4 requested but not yet confirmed by the server: hold
			// tramo 3 so no tramo-4 line is emitted while the pot may move.
			m_Tramo = 3;
			m_SmoothS = 0.8;
		}
		if (m_Inject == "smooth03")
		{
			m_SmoothS = 0.3;
		}
		if (prevTramo != m_Tramo && m_Tramo != 4)
		{
			STRACK_Move.SendCaseState(m_Caso, m_Tramo, false);
		}
		if (!m_SuaveBaseDone)
		{
			STRACK_Math.Copy4(lataTm, tryAxes);
			tryAxes[3] = m_LataPos;
			BuildFollow(m_LataPos, tryAxes, tryMat);
			STRACK_Math.MatQuat(tryMat, qa);
			cand[0] = 0.0;
			cand[1] = 45.0;
			cand[2] = -45.0;
			cand[3] = 90.0;
			cand[4] = -90.0;
			cand[5] = 135.0;
			cand[6] = -135.0;
			cand[7] = 180.0;
			m_SuaveBaseRot = 0.0;
			bestDot = 2.0;
			ci = 0;
			while (ci < 8)
			{
				STRACK_Math.YawWorld(tryMat, cand[ci], rawYaw);
				STRACK_Math.MatQuat(rawYaw, qa);
				STRACK_Math.YawWorld(tryMat, cand[ci] + 170.0, rawYaw);
				STRACK_Math.MatQuat(rawYaw, qb);
				dTry = STRACK_Math.QuatDot(qa, qb);
				if (dTry < bestDot)
				{
					bestDot = dTry;
					m_SuaveBaseRot = cand[ci];
				}
				ci = ci + 1;
			}
			if (bestDot >= 0.0)
			{
				m_SuaveBaseRot = 0.0;
			}
			m_SuaveBaseDone = true;
			Print("[STRACK] suave base_rot=" + STRACK_Math.N(m_SuaveBaseRot) + " dot_previsto=" + STRACK_Math.N(bestDot));
		}
		STRACK_Math.YawWorld(lataTm, m_SuaveBaseRot, axesRot);
		axesRot[3] = m_LataPos;
		BuildFollow(m_LataPos, axesRot, raw);
		m_GiroSuave = 0;
		yawOff = 0.0;
		if (m_Tramo == 4 && m_Tramo4Ack)
		{
			t4 = m_Now - m_Tramo4T0;
			if (t4 >= 0.5 && t4 < 4.5)
			{
				m_GiroSuave = 1;
				yawOff = 170.0;
			}
			else if (t4 >= 4.5 && t4 < 8.5)
			{
				m_GiroSuave = 2;
				yawOff = 0.0;
			}
		}
		if (yawOff != 0.0)
		{
			STRACK_Math.YawWorld(raw, yawOff, rawYaw);
			STRACK_Math.Copy4(rawYaw, raw);
		}
		STRACK_Math.Copy4(raw, used);
		mode = 0;
		if (m_Inject == "quatlerp")
		{
			mode = 1;
		}
		if (m_Inject == "longarc")
		{
			mode = 2;
		}
		alpha = 1.0;
		if (m_SmoothS > 0.0 && m_FiltOn && m_Dt > 0.0)
		{
			alpha = 1.0 - STRACK_Math.Exp(-m_Dt / m_SmoothS);
		}
		if (m_GiroSuave != 0 && m_GiroSuave != m_PrevGiroSuave)
		{
			if (m_FiltOn)
			{
				STRACK_Math.MatQuat(m_Filt, qa);
			}
			else
			{
				STRACK_Math.MatQuat(used, qa);
			}
			STRACK_Math.MatQuat(raw, qb);
			m_QuatDot = STRACK_Math.QuatDot(qa, qb);
			m_QuatDotPending = true;
		}
		if (!m_FiltOn)
		{
			STRACK_Math.Copy4(used, m_Filt);
			m_FiltOn = true;
		}
		else
		{
			STRACK_Math.SlerpMode(m_Filt, used, alpha, mode, filtered);
			filtered[3] = m_Filt[3] + (used[3] - m_Filt[3]) * alpha;
			STRACK_Math.Copy4(filtered, m_Filt);
		}
		STRACK_Math.Copy4(m_Filt, used);
		m_PrevGiroSuave = m_GiroSuave;
		STRACK_Math.Copy4(raw, m_Prev);
		m_HasRaw = true;
		STRACK_Math.Copy4(used, m_Written);
		STRACK_Math.Copy4(used, written);
		STRACK_Math.MatQuat(m_Written, m_WrittenQ);
		STRACK_Math.Copy4(raw, m_CamRaw);
		STRACK_Math.MatQuat(m_CamRaw, m_RawQ);
		WriteCamera(weapon, used);
		return true;
	}

	protected void BuildMount(vector usti, vector konec, vector axes[4], out vector raw[4])
	{
		vector camPos;
		camPos = usti + axes[0] * 0.6 + axes[1] * 0.1;
		STRACK_Math.Look(camPos, konec, axes[1], raw);
	}

	protected void BuildFollow(vector usti, vector axes[4], out vector raw[4])
	{
		vector fwd;
		vector camPos;
		fwd = axes[2];
		fwd[1] = 0;
		if (fwd.Length() < 0.001)
		{
			fwd = Vector(0, 0, 1);
		}
		fwd.Normalize();
		// Orquestador 2026-11-11: 2,0/0,5 m daba 138 px boca-recamara con f = 684 px; escalado a 0,6
		// (1,2/0,3 m) da 233 px de mediana y 231 px de p05 sobre las muestras reales de follow_Ha.
		camPos = usti - fwd * 1.2 + Vector(0, 0.3, 0);
		STRACK_Math.Look(camPos, usti, Vector(0, 1, 0), raw);
	}

	protected void WriteCamera(EntityAI weapon, vector pose[4])
	{
		vector inv[4];
		vector localPose[4];
		vector weaponTm[4];
		if (!m_Cam)
		{
			return;
		}
		m_Cam.SetFOV(m_Fov);
		m_Cam.SetActive(true);
		if (m_Hook == "Hc")
		{
			if (!m_Attached || m_Inject == "delay1")
			{
				weapon.GetTransform(weaponTm);
				STRACK_Math.Copy4(weaponTm, inv);
				Math3D.MatrixInverse4(inv);
				Math3D.MatrixMultiply4(inv, pose, localPose);
				if (!m_Attached)
				{
					weapon.AddChild(m_Cam, -1, false);
					m_Parent = weapon;
					m_Attached = true;
					Print("[STRACK] H-c AddChild pivot -1");
				}
				m_Cam.SetTransform(localPose);
			}
			return;
		}
		m_Cam.SetTransform(pose);
	}

	// Brief v1.1 B: 0/10 deg per frame from a fixed-seed sequence (two LCG
	// steps mod 65536 of the frame number, seed 12345); the evaluator reads it
	// back from calib_yaw_deg. Products stay below 2^31.
	static bool CalibBit(int frame)
	{
		int s1;
		int s2;
		s1 = (frame * 25173 + 13849) % 65536;
		s2 = (s1 * 25173 + 13849 + 12345) % 65536;
		return s2 >= 32768;
	}

	protected void ApplyShot()
	{
		bool want;
		string path;
		want = false;
		m_Shot = "";
		if (CurrentGiro() > 0)
		{
			if ((m_Frame % 2) == 0)
			{
				want = true;
			}
		}
		else if ((m_Frame % 10) == 0)
		{
			want = true;
		}
		if (!want)
		{
			return;
		}
		m_Shot = STRACK_Math.FrameBmp(m_Frame);
		path = "$profile:strack/" + m_Run + "/" + m_Shot;
		MakeScreenshot(path);
		m_Shots = m_Shots + 1;
	}

	protected string ReadJson(int index)
	{
		vector v;
		if (m_Ok.Get(index) == 0)
		{
			return "null";
		}
		v = Vector(m_Px.Get(index), m_Py.Get(index), m_Pz.Get(index));
		return STRACK_Math.V(v - m_Origin);
	}

	protected string PointJson(int point)
	{
		int base;
		string s;
		base = point * 6;
		s = "{\"a\":" + ReadJson(base);
		s = s + ",\"b\":" + ReadJson(base + 1);
		s = s + ",\"c\":" + ReadJson(base + 2);
		s = s + ",\"d\":" + ReadJson(base + 3);
		s = s + ",\"e\":" + ReadJson(base + 4);
		s = s + ",\"f\":" + ReadJson(base + 5) + "}";
		return s;
	}

	protected string PoseJson(vector tm[4], vector pos)
	{
		string s;
		s = "{\"pos\":" + STRACK_Math.V(pos - m_Origin);
		s = s + ",\"x\":" + STRACK_Math.V(tm[0]);
		s = s + ",\"y\":" + STRACK_Math.V(tm[1]);
		s = s + ",\"z\":" + STRACK_Math.V(tm[2]) + "}";
		return s;
	}

	protected string EntityPoseJson(EntityAI ent)
	{
		vector tm[4];
		vector fm[4];
		string s;
		if (!ent)
		{
			return "null";
		}
		ent.GetTransform(tm);
		ent.GetTransform(fm);
		s = "{\"a\":" + PoseJson(tm, tm[3]);
		s = s + ",\"f\":" + PoseJson(fm, ent.GetWorldPosition()) + "}";
		return s;
	}

	protected string SpinePoseJson(PlayerBase player)
	{
		vector ws[4];
		vector ms[4];
		vector pm[4];
		vector prod[4];
		string s;
		if (!player)
		{
			return "null";
		}
		if (!m_SpineChecked)
		{
			m_SpineBone = player.GetBoneIndexByName("Spine3");
			m_SpineChecked = true;
			if (m_SpineBone == -1)
			{
				Print("[STRACK] Spine3 ausente (-1)");
			}
		}
		if (m_SpineBone == -1)
		{
			return "null";
		}
		player.GetBoneTransformWS(m_SpineBone, ws);
		player.GetBoneTransformMS(m_SpineBone, ms);
		player.GetTransform(pm);
		pm[3] = player.GetWorldPosition();
		Math3D.MatrixMultiply4(pm, ms, prod);
		s = "{\"a\":" + PoseJson(ws, ws[3]);
		s = s + ",\"f\":" + PoseJson(prod, prod[3]) + "}";
		return s;
	}

	protected string RopaJson(PlayerBase player, EntityAI weapon)
	{
		EntityAI mochila;
		EntityAI mira;
		EntityAI sil;
		string s;
		mochila = null;
		mira = null;
		sil = null;
		if (player)
		{
			mochila = FindByType(player, "AliceBag_Green");
		}
		if (weapon)
		{
			mira = FindByType(weapon, "ACOGOptic");
			sil = FindByType(weapon, "M4_Suppressor");
		}
		s = "{\"mochila\":" + EntityPoseJson(mochila);
		s = s + ",\"mira\":" + EntityPoseJson(mira);
		s = s + ",\"silenciador\":" + EntityPoseJson(sil);
		s = s + ",\"spine3\":" + SpinePoseJson(player);
		s = s + ",\"arma\":" + EntityPoseJson(weapon) + "}";
		return s;
	}

	protected void WriteLine(int invocations)
	{
		string line;
		float tMs;
		if (!m_FileOpen)
		{
			return;
		}
		tMs = (m_Now - m_T0) * 1000.0;
		line = "{\"frame\":" + m_Frame.ToString();
		line = line + ",\"t_ms\":" + STRACK_Math.N(tMs);
		line = line + ",\"dt\":" + STRACK_Math.N(m_Dt);
		line = line + ",\"hook\":\"" + m_Hook + "\"";
		line = line + ",\"invocaciones_en_frame\":" + invocations.ToString();
		line = line + ",\"caso\":\"" + m_Caso + "\"";
		line = line + ",\"inject\":\"" + m_Inject + "\"";
		line = line + ",\"run\":\"" + m_Run + "\"";
		line = line + ",\"giro\":" + m_FrozenGiro.ToString();
		line = line + ",\"seg\":" + m_FrozenSeg.ToString();
		line = line + ",\"lecturas\":{\"usti hlavne\":" + PointJson(0);
		line = line + ",\"konec hlavne\":" + PointJson(1);
		if (m_Caso == "ropa")
		{
			if (m_MiraOk)
			{
				line = line + ",\"mira\":" + PointJson(2);
			}
			else
			{
				line = line + ",\"mira\":null";
			}
		}
		line = line + "}";
		line = line + ",\"origin\":" + STRACK_Math.V(m_Origin);
		line = line + ",\"cam\":{\"pos\":" + STRACK_Math.V(m_Written[3] - m_Origin);
		line = line + ",\"x\":" + STRACK_Math.V(m_Written[0]);
		line = line + ",\"y\":" + STRACK_Math.V(m_Written[1]);
		line = line + ",\"z\":" + STRACK_Math.V(m_Written[2]);
		if (IsSuave())
		{
			line = line + ",\"q\":" + STRACK_Math.Q(m_WrittenQ);
		}
		line = line + "}";
		line = line + ",\"fov_rad\":1.0471976";
		line = line + ",\"fov_motor\":" + STRACK_Math.N(Camera.GetCurrentFOV());
		line = line + ",\"calib_yaw_deg\":" + STRACK_Math.N(m_Yaw);
		if (m_Caso == "ropa")
		{
			line = line + ",\"ropa\":" + m_FrozenRopa;
		}
		if (IsSuave())
		{
			line = line + ",\"tramo\":" + m_Tramo.ToString();
			line = line + ",\"smooth_s\":" + STRACK_Math.N(m_SmoothS);
			line = line + ",\"fps_cap\":" + m_FpsCap.ToString();
			if (m_LataOk)
			{
				line = line + ",\"lata\":{\"a\":" + STRACK_Math.V(m_LataPos - m_Origin) + "}";
			}
			else
			{
				line = line + ",\"lata\":{\"a\":null}";
			}
			line = line + ",\"cam_raw\":{\"pos\":" + STRACK_Math.V(m_CamRaw[3] - m_Origin);
			line = line + ",\"x\":" + STRACK_Math.V(m_CamRaw[0]);
			line = line + ",\"y\":" + STRACK_Math.V(m_CamRaw[1]);
			line = line + ",\"z\":" + STRACK_Math.V(m_CamRaw[2]);
			line = line + ",\"q\":" + STRACK_Math.Q(m_RawQ) + "}";
			if (m_QuatDotPending)
			{
				line = line + ",\"quat_dot_inicio\":" + STRACK_Math.N(m_QuatDot);
				m_QuatDotPending = false;
			}
		}
		line = line + ",\"shot\":\"" + m_Shot + "\"}";
		FPrintln(m_File, line);
		m_Samples = m_Samples + 1;
	}

	protected void FlushHb()
	{
		if (!m_HbOpen)
		{
			return;
		}
		WriteLine(m_HbInv);
		m_HbOpen = false;
	}

	protected void Finish(string why)
	{
		string done;
		FileHandle doneFile;
		if (m_Done)
		{
			return;
		}
		m_Done = true;
		if (IsSuave())
		{
			STRACK_Move.SendCaseState(m_Caso, m_Tramo, true);
		}
		FlushHb();
		if (m_Attached && m_Parent && m_Cam)
		{
			m_Parent.RemoveChild(m_Cam, true);
			Print("[STRACK] H-c RemoveChild keepTransform");
		}
		if (m_Cam)
		{
			m_Cam.SetActive(false);
		}
		if (m_FileOpen)
		{
			CloseFile(m_File);
			m_FileOpen = false;
		}
		done = "{\"run\":\"" + m_Run + "\",\"frames\":" + m_Samples.ToString() + ",\"shots\":" + m_Shots.ToString() + ",\"ok\":true,\"preflight_dt_p50_ms\":" + STRACK_Math.N(m_PfP50) + "}";
		doneFile = OpenFile("$profile:strack/" + m_Run + "/done.json", FileMode.WRITE);
		if (doneFile != 0)
		{
			FPrintln(doneFile, done);
			CloseFile(doneFile);
		}
		else
		{
			Print("[STRACK] no se abre done.json");
		}
		STRACK_Move.Stop();
		Print("[STRACK] fin " + why + " frames=" + m_Samples.ToString() + " shots=" + m_Shots.ToString());
	}
};
