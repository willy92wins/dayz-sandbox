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

	void STRACK_Session()
	{
		int i;
		m_Ok = new array<int>();
		m_Px = new array<float>();
		m_Py = new array<float>();
		m_Pz = new array<float>();
		i = 0;
		while (i < 12)
		{
			m_Ok.Insert(0);
			m_Px.Insert(0);
			m_Py.Insert(0);
			m_Pz.Insert(0);
			i = i + 1;
		}
		m_Fov = 1.0471976;
		m_Frame = -1;
		m_Inject = "none";
		m_Hook = "";
		m_Caso = "";
		m_Shot = "";
		m_Bone = -1;
		m_HbFrame = -1;
		m_HandsSince = -1.0;
		m_ArmWait = 60.0;
	}

	static bool Running()
	{
		if (!s_Me)
		{
			return false;
		}
		return s_Me.m_RunOn && !s_Me.m_Done;
	}

	protected void Tick(float dt)
	{
		PlayerBase player;
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
		if (!m_Armed)
		{
			if (!TryArm())
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
		casoOk = false;
		if (m_Caso == "calib" || m_Caso == "mount0" || m_Caso == "mount03" || m_Caso == "lookat" || m_Caso == "follow")
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
		if (m_Inject != "none" && m_Inject != "delay1" && m_Inject != "roll")
		{
			Print("[STRACK] inject no valido: " + m_Inject);
			return false;
		}
		if (m_Hook == "Hc" && m_Caso != "mount0")
		{
			Print("[STRACK] H-c solo vale para mount0");
			return false;
		}
		if (m_Caso == "calib" && m_Hook == "Hc")
		{
			return false;
		}
		if (m_Caso == "mount03" && m_Hook == "Hc")
		{
			return false;
		}
		if (m_Caso == "lookat" && m_Hook == "Hc")
		{
			return false;
		}
		if (m_Caso == "follow" && m_Hook == "Hc")
		{
			return false;
		}
		return true;
	}

	protected bool TryArm()
	{
		PlayerBase player;
		HumanInventory inv;
		EntityAI weapon;
		Object created;
		vector pos;
		vector fwd;
		float heading;
		HumanInputController hic;
		player = PlayerBase.Cast(GetGame().GetPlayer());
		if (!player)
		{
			return false;
		}
		inv = player.GetHumanInventory();
		if (!inv)
		{
			return false;
		}
		weapon = inv.GetEntityInHands();
		if (!weapon)
		{
			m_HandsSince = -1.0;
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
		if (m_Self)
		{
			STRACK_Move.Begin(m_Caso == "lookat");
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
		if (weapon && player)
		{
			FillReadings(player, weapon);
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
		ApplyShot();
		if (writeNow)
		{
			WriteLine(1);
		}
	}

	protected void ClearAllReadings()
	{
		int i;
		i = 0;
		while (i < 12)
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
		if ((m_Frame % 10) == 0)
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
		line = line + ",\"lecturas\":{\"usti hlavne\":" + PointJson(0);
		line = line + ",\"konec hlavne\":" + PointJson(1) + "}";
		line = line + ",\"origin\":" + STRACK_Math.V(m_Origin);
		line = line + ",\"cam\":{\"pos\":" + STRACK_Math.V(m_Written[3] - m_Origin);
		line = line + ",\"x\":" + STRACK_Math.V(m_Written[0]);
		line = line + ",\"y\":" + STRACK_Math.V(m_Written[1]);
		line = line + ",\"z\":" + STRACK_Math.V(m_Written[2]) + "}";
		line = line + ",\"fov_rad\":1.0471976";
		line = line + ",\"fov_motor\":" + STRACK_Math.N(Camera.GetCurrentFOV());
		line = line + ",\"calib_yaw_deg\":" + STRACK_Math.N(m_Yaw);
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
		done = "{\"run\":\"" + m_Run + "\",\"frames\":" + m_Samples.ToString() + ",\"shots\":" + m_Shots.ToString() + ",\"ok\":true}";
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
