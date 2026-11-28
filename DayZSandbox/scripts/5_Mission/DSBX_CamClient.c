class DSBX_CamClient : DSBX_CamEngine
{
	Camera m_Cam;
	bool m_Active;
	bool m_Playing;
	bool m_HudCaptured;
	string m_CamId;
	float m_T;
	float m_Dur;
	int m_SavedHudFlagsMask;
	int m_SavedAuxVisMask;
	ref array<string> m_AuxWidgetNames;
	ref array<float> m_KeyT;
	ref array<vector> m_KeyPos;
	ref array<vector> m_KeyYpr;
	ref array<float> m_KeyFovRad;
	ref array<float> m_KeyFocus;
	ref array<float> m_KeyQ0;
	ref array<float> m_KeyQ1;
	ref array<float> m_KeyQ2;
	ref array<float> m_KeyQ3;

	void DSBX_CamClient()
	{
		m_Cam = null;
		m_Active = false;
		m_Playing = false;
		m_HudCaptured = false;
		m_CamId = "";
		m_T = 0.0;
		m_Dur = 0.0;
		m_SavedHudFlagsMask = 0;
		m_SavedAuxVisMask = 0;
		m_AuxWidgetNames = new array<string>();
		m_AuxWidgetNames.Insert("CursorIcons");
		m_AuxWidgetNames.Insert("PermanentCrossHair");
		m_AuxWidgetNames.Insert("WalkieTalkie");
		m_AuxWidgetNames.Insert("ActionTargetsCursorWidget");
		m_AuxWidgetNames.Insert("StaminaBar");
		m_AuxWidgetNames.Insert("StaminaBackground");
		m_AuxWidgetNames.Insert("GameStatusIcons");
		m_KeyT = new array<float>();
		m_KeyPos = new array<vector>();
		m_KeyYpr = new array<vector>();
		m_KeyFovRad = new array<float>();
		m_KeyFocus = new array<float>();
		m_KeyQ0 = new array<float>();
		m_KeyQ1 = new array<float>();
		m_KeyQ2 = new array<float>();
		m_KeyQ3 = new array<float>();
	}

	override string Play(DSBX_Args args)
	{
		if (!args)
		{
			return "bad_args";
		}
		if (args.cam_id == "")
		{
			return "bad_args";
		}
		if (!args.c_t_ms || !args.c_x_mm || !args.c_y_mm || !args.c_z_mm || !args.c_yaw_mdeg || !args.c_pitch_mdeg || !args.c_fov_mdeg || !args.c_focus_mm)
		{
			return "bad_args";
		}
		int n = args.c_t_ms.Count();
		if (n < 1 || n > DSBX_Const.CAM_MAX_KEYS)
		{
			return "bad_args";
		}
		if (args.c_x_mm.Count() != n || args.c_y_mm.Count() != n || args.c_z_mm.Count() != n || args.c_yaw_mdeg.Count() != n || args.c_pitch_mdeg.Count() != n || args.c_fov_mdeg.Count() != n || args.c_focus_mm.Count() != n)
		{
			return "bad_args";
		}
		if (args.c_t_ms.Get(0) != 0)
		{
			return "bad_args";
		}
		int i = 0;
		while (i < n)
		{
			if (i > 0 && args.c_t_ms.Get(i) <= args.c_t_ms.Get(i - 1))
			{
				return "bad_args";
			}
			int yaw = args.c_yaw_mdeg.Get(i);
			int pitch = args.c_pitch_mdeg.Get(i);
			int fov = args.c_fov_mdeg.Get(i);
			int focus = args.c_focus_mm.Get(i);
			if (yaw < 0 || yaw >= 360000)
			{
				return "bad_args";
			}
			if (pitch < -90000 || pitch > 90000)
			{
				return "bad_args";
			}
			if (fov <= 0 || fov >= 180000)
			{
				return "bad_args";
			}
			if (focus <= 0)
			{
				return "bad_args";
			}
			i = i + 1;
		}
		if (m_Playing)
		{
			return "busy";
		}
		bool firstActivation = !m_Active;
		ClearKeys();
		int k = 0;
		while (k < n)
		{
			float xm = args.c_x_mm.Get(k) / 1000.0;
			float ym = args.c_y_mm.Get(k) / 1000.0;
			float zm = args.c_z_mm.Get(k) / 1000.0;
			float yAbs = ym;
			if (g_Game)
			{
				yAbs = g_Game.SurfaceY(xm, zm) + ym;
			}
			vector pos = Vector(xm, yAbs, zm);
			float yawDeg = args.c_yaw_mdeg.Get(k) / 1000.0;
			float pitchDeg = args.c_pitch_mdeg.Get(k) / 1000.0;
			vector ypr = Vector(yawDeg, pitchDeg, 0);
			float fovRad = (args.c_fov_mdeg.Get(k) / 1000.0) * Math.DEG2RAD;
			float focusM = args.c_focus_mm.Get(k) / 1000.0;
			vector rot[3];
			Math3D.YawPitchRollMatrix(ypr, rot);
			float kq[4];
			Math3D.MatrixToQuat(rot, kq);
			m_KeyT.Insert(args.c_t_ms.Get(k));
			m_KeyPos.Insert(pos);
			m_KeyYpr.Insert(ypr);
			m_KeyFovRad.Insert(fovRad);
			m_KeyFocus.Insert(focusM);
			m_KeyQ0.Insert(kq[0]);
			m_KeyQ1.Insert(kq[1]);
			m_KeyQ2.Insert(kq[2]);
			m_KeyQ3.Insert(kq[3]);
			k = k + 1;
		}
		m_CamId = args.cam_id;
		m_T = 0.0;
		m_Dur = args.c_t_ms.Get(n - 1);
		if (firstActivation)
		{
			HideHudAndSaveState();
			SetPlayerControlDisabled(true);
		}
		ApplyAt(0.0);
		m_Active = true;
		if (m_Dur > 0.0)
		{
			m_Playing = true;
		}
		else
		{
			m_Playing = false;
		}
		return "";
	}

	override string Stop()
	{
		if (!m_Active)
		{
			return "";
		}
		DestroyCam();
		RestoreHudSavedState();
		SetPlayerControlDisabled(false);
		m_Active = false;
		m_Playing = false;
		m_HudCaptured = false;
		m_CamId = "";
		m_T = 0.0;
		m_Dur = 0.0;
		ClearKeys();
		return "";
	}

	override string ReadJson()
	{
		int activeN = 0;
		int playingN = 0;
		string camId = "";
		int tMs = 0;
		int durMs = 0;
		int xMm = 0;
		int yMm = 0;
		int zMm = 0;
		int yawMdeg = 0;
		int pitchMdeg = 0;
		int fovMdeg = 0;
		if (m_Active)
		{
			activeN = 1;
			if (m_Playing)
			{
				playingN = 1;
			}
			camId = m_CamId;
			tMs = (int)Math.Round(m_T);
			durMs = (int)Math.Round(m_Dur);
			if (g_Game)
			{
				vector pos = g_Game.GetCurrentCameraPosition();
				vector dir = g_Game.GetCurrentCameraDirection();
				float fovRad = Camera.GetCurrentFOV();
				xMm = (int)Math.Round(pos[0] * 1000.0);
				yMm = (int)Math.Round(pos[1] * 1000.0);
				zMm = (int)Math.Round(pos[2] * 1000.0);
				float yawDeg = Math.Atan2(dir[0], dir[2]) * Math.RAD2DEG;
				while (yawDeg < 0.0)
				{
					yawDeg = yawDeg + 360.0;
				}
				while (yawDeg >= 360.0)
				{
					yawDeg = yawDeg - 360.0;
				}
				yawMdeg = (int)Math.Round(yawDeg * 1000.0);
				if (yawMdeg >= 360000)
				{
					yawMdeg = 0;
				}
				float dy = dir[1];
				if (dy < -1.0)
				{
					dy = -1.0;
				}
				if (dy > 1.0)
				{
					dy = 1.0;
				}
				float pitchDeg = Math.Asin(dy) * Math.RAD2DEG;
				pitchMdeg = (int)Math.Round(pitchDeg * 1000.0);
				fovMdeg = (int)Math.Round(fovRad * Math.RAD2DEG * 1000.0);
			}
		}
		string camIdJson = DSBX_Wire.WireText(camId);
		string body = "{\"cam\":{\"active\":" + activeN.ToString();
		body = body + ",\"playing\":" + playingN.ToString();
		body = body + ",\"cam_id\":" + camIdJson;
		body = body + ",\"t_ms\":" + tMs.ToString();
		body = body + ",\"dur_ms\":" + durMs.ToString();
		body = body + ",\"pose\":[" + xMm.ToString();
		body = body + "," + yMm.ToString();
		body = body + "," + zMm.ToString();
		body = body + "," + yawMdeg.ToString();
		body = body + "," + pitchMdeg.ToString();
		body = body + "," + fovMdeg.ToString() + "]}}";
		return body;
	}

	override void Tick(float timeslice)
	{
		if (!m_Playing)
		{
			return;
		}
		m_T = m_T + timeslice * 1000.0;
		if (m_T >= m_Dur)
		{
			m_T = m_Dur;
			ApplyAt(m_Dur);
			m_Playing = false;
			return;
		}
		ApplyAt(m_T);
	}

	void ClearKeys()
	{
		m_KeyT.Clear();
		m_KeyPos.Clear();
		m_KeyYpr.Clear();
		m_KeyFovRad.Clear();
		m_KeyFocus.Clear();
		m_KeyQ0.Clear();
		m_KeyQ1.Clear();
		m_KeyQ2.Clear();
		m_KeyQ3.Clear();
	}

	void DestroyCam()
	{
		if (m_Cam)
		{
			ApplyCamFocus(0.0, 0.0);
			m_Cam.SetActive(false);
			if (g_Game)
			{
				g_Game.ObjectDelete(m_Cam);
			}
			m_Cam = null;
		}
	}

	void CopyRotToMat4(vector rot[3], vector pos, out vector mat4[4])
	{
		mat4[0] = rot[0];
		mat4[1] = rot[1];
		mat4[2] = rot[2];
		mat4[3] = pos;
	}

	void SlerpQuat(float qa[4], float qb[4], float u, out float qout[4])
	{
		float na = Math.Sqrt(qa[0] * qa[0] + qa[1] * qa[1] + qa[2] * qa[2] + qa[3] * qa[3]);
		float ax = 0.0;
		float ay = 0.0;
		float az = 0.0;
		float aw = 1.0;
		if (na > 0.000001)
		{
			ax = qa[0] / na;
			ay = qa[1] / na;
			az = qa[2] / na;
			aw = qa[3] / na;
		}
		float nb = Math.Sqrt(qb[0] * qb[0] + qb[1] * qb[1] + qb[2] * qb[2] + qb[3] * qb[3]);
		float bx = 0.0;
		float by = 0.0;
		float bz = 0.0;
		float bw = 1.0;
		if (nb > 0.000001)
		{
			bx = qb[0] / nb;
			by = qb[1] / nb;
			bz = qb[2] / nb;
			bw = qb[3] / nb;
		}
		float d = ax * bx + ay * by + az * bz + aw * bw;
		if (d < 0.0)
		{
			bx = -bx;
			by = -by;
			bz = -bz;
			bw = -bw;
			d = -d;
		}
		float ox;
		float oy;
		float oz;
		float ow;
		if (d > 0.9995)
		{
			ox = ax + u * (bx - ax);
			oy = ay + u * (by - ay);
			oz = az + u * (bz - az);
			ow = aw + u * (bw - aw);
		}
		else
		{
			float dc = Math.Clamp(d, -1.0, 1.0);
			float omega = Math.Acos(dc);
			float sinO = Math.Sin(omega);
			float w0 = Math.Sin((1.0 - u) * omega) / sinO;
			float w1 = Math.Sin(u * omega) / sinO;
			ox = w0 * ax + w1 * bx;
			oy = w0 * ay + w1 * by;
			oz = w0 * az + w1 * bz;
			ow = w0 * aw + w1 * bw;
		}
		float no = Math.Sqrt(ox * ox + oy * oy + oz * oz + ow * ow);
		if (no > 0.000001)
		{
			qout[0] = ox / no;
			qout[1] = oy / no;
			qout[2] = oz / no;
			qout[3] = ow / no;
		}
		else
		{
			qout[0] = 0.0;
			qout[1] = 0.0;
			qout[2] = 0.0;
			qout[3] = 1.0;
		}
	}

	MissionGameplay GetMissionGameplay()
	{
		if (!g_Game)
		{
			return null;
		}
		return MissionGameplay.Cast(g_Game.GetMission());
	}

	IngameHud GetIngameHud()
	{
		MissionGameplay mg = GetMissionGameplay();
		if (!mg)
		{
			return null;
		}
		return mg.m_Hud;
	}

	void SetPlayerControlDisabled(bool disabled)
	{
		MissionGameplay mg = GetMissionGameplay();
		if (!mg)
		{
			return;
		}
		if (disabled)
		{
			mg.PlayerControlDisable(INPUT_EXCLUDE_ALL);
		}
		else
		{
			mg.PlayerControlEnable(true);
		}
	}

	bool EnsureActiveCam(vector pos, vector yprDeg, float fovRad)
	{
		if (!g_Game)
		{
			return false;
		}
		if (!m_Cam)
		{
			m_Cam = Camera.Cast(g_Game.CreateObject("staticcamera", pos, true));
		}
		if (!m_Cam)
		{
			return false;
		}
		vector rot[3];
		Math3D.YawPitchRollMatrix(yprDeg, rot);
		vector mat4[4];
		CopyRotToMat4(rot, pos, mat4);
		m_Cam.SetTransform(mat4);
		m_Cam.SetFOV(fovRad);
		m_Cam.SetActive(true);
		return true;
	}

	void ApplyCamFocus(float distM, float blur)
	{
		if (m_Cam)
		{
			m_Cam.SetFocus(distM, blur);
		}
	}

	int ReadHudFlagsMask()
	{
		IngameHud hud = GetIngameHud();
		if (!hud)
		{
			return 0;
		}
		IngameHudVisibility vis = hud.GetHudVisibility();
		if (!vis)
		{
			return 0;
		}
		int mask = 0;
		if (vis.IsContextFlagActive(EHudContextFlags.HUD_DISABLE))
		{
			mask = mask | 1;
		}
		if (vis.IsContextFlagActive(EHudContextFlags.HUD_HIDE))
		{
			mask = mask | 2;
		}
		if (vis.IsContextFlagActive(EHudContextFlags.VEHICLE_DISABLE))
		{
			mask = mask | 4;
		}
		if (vis.IsContextFlagActive(EHudContextFlags.DRIVER))
		{
			mask = mask | 8;
		}
		if (vis.IsContextFlagActive(EHudContextFlags.VEHICLE))
		{
			mask = mask | 16;
		}
		if (vis.IsContextFlagActive(EHudContextFlags.MENU_OPEN))
		{
			mask = mask | 32;
		}
		if (vis.IsContextFlagActive(EHudContextFlags.NO_BADGE))
		{
			mask = mask | 64;
		}
		if (vis.IsContextFlagActive(EHudContextFlags.QUICKBAR_DISABLE))
		{
			mask = mask | 128;
		}
		if (vis.IsContextFlagActive(EHudContextFlags.QUICKBAR_HIDE))
		{
			mask = mask | 256;
		}
		if (vis.IsContextFlagActive(EHudContextFlags.QUICKBAR_GLOBAL))
		{
			mask = mask | 512;
		}
		if (vis.IsContextFlagActive(EHudContextFlags.INVENTORY_OPEN))
		{
			mask = mask | 1024;
		}
		if (vis.IsContextFlagActive(EHudContextFlags.UNCONSCIOUS))
		{
			mask = mask | 2048;
		}
		return mask;
	}

	void ApplyHudFlagsMask(int mask)
	{
		IngameHud hud = GetIngameHud();
		if (!hud)
		{
			return;
		}
		IngameHudVisibility vis = hud.GetHudVisibility();
		if (!vis)
		{
			return;
		}
		vis.SetContextFlag(EHudContextFlags.HUD_DISABLE, (mask & 1) != 0);
		vis.SetContextFlag(EHudContextFlags.HUD_HIDE, (mask & 2) != 0);
		vis.SetContextFlag(EHudContextFlags.VEHICLE_DISABLE, (mask & 4) != 0);
		vis.SetContextFlag(EHudContextFlags.DRIVER, (mask & 8) != 0);
		vis.SetContextFlag(EHudContextFlags.VEHICLE, (mask & 16) != 0);
		vis.SetContextFlag(EHudContextFlags.MENU_OPEN, (mask & 32) != 0);
		vis.SetContextFlag(EHudContextFlags.NO_BADGE, (mask & 64) != 0);
		vis.SetContextFlag(EHudContextFlags.QUICKBAR_DISABLE, (mask & 128) != 0);
		vis.SetContextFlag(EHudContextFlags.QUICKBAR_HIDE, (mask & 256) != 0);
		vis.SetContextFlag(EHudContextFlags.QUICKBAR_GLOBAL, (mask & 512) != 0);
		vis.SetContextFlag(EHudContextFlags.INVENTORY_OPEN, (mask & 1024) != 0);
		vis.SetContextFlag(EHudContextFlags.UNCONSCIOUS, (mask & 2048) != 0);
	}

	int ReadAuxVisMask()
	{
		IngameHud hud = GetIngameHud();
		if (!hud)
		{
			return 0;
		}
		Widget panel = hud.GetHudPanelWidget();
		if (!panel)
		{
			return 0;
		}
		int mask = 0;
		int i = 0;
		while (i < m_AuxWidgetNames.Count())
		{
			Widget w = panel.FindAnyWidget(m_AuxWidgetNames.Get(i));
			if (w && w.IsVisible())
			{
				mask = mask | (1 << i);
			}
			i = i + 1;
		}
		return mask;
	}

	void ApplyAuxVisMask(int mask)
	{
		IngameHud hud = GetIngameHud();
		if (!hud)
		{
			return;
		}
		Widget panel = hud.GetHudPanelWidget();
		if (!panel)
		{
			return;
		}
		int i = 0;
		while (i < m_AuxWidgetNames.Count())
		{
			Widget w = panel.FindAnyWidget(m_AuxWidgetNames.Get(i));
			if (w)
			{
				w.Show((mask & (1 << i)) != 0);
			}
			i = i + 1;
		}
	}

	void HideHudAndSaveState()
	{
		m_SavedHudFlagsMask = ReadHudFlagsMask();
		m_SavedAuxVisMask = ReadAuxVisMask();
		m_HudCaptured = true;
		IngameHud hud = GetIngameHud();
		if (hud)
		{
			IngameHudVisibility vis = hud.GetHudVisibility();
			if (vis)
			{
				vis.SetContextFlag(EHudContextFlags.INVENTORY_OPEN, false);
				vis.SetContextFlag(EHudContextFlags.HUD_DISABLE, true);
				vis.SetContextFlag(EHudContextFlags.HUD_HIDE, true);
				vis.SetContextFlag(EHudContextFlags.VEHICLE_DISABLE, true);
				vis.SetContextFlag(EHudContextFlags.QUICKBAR_DISABLE, true);
				vis.SetContextFlag(EHudContextFlags.QUICKBAR_HIDE, true);
			}
		}
		ApplyAuxVisMask(0);
	}

	void RestoreHudSavedState()
	{
		ApplyHudFlagsMask(m_SavedHudFlagsMask);
		ApplyAuxVisMask(m_SavedAuxVisMask);
	}

	vector CatmullPos(vector p0, vector p1, vector p2, vector p3, float u)
	{
		float u2 = u * u;
		float u3 = u2 * u;
		return 0.5 * (2.0 * p1 + (-p0 + p2) * u + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * u2 + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * u3);
	}

	void ApplyAt(float tMs)
	{
		int n = m_KeyT.Count();
		if (n < 1)
		{
			return;
		}
		vector pos;
		vector ypr;
		float fovRad;
		float focusM;
		if (n == 1 || tMs <= m_KeyT.Get(0))
		{
			pos = m_KeyPos.Get(0);
			ypr = m_KeyYpr.Get(0);
			fovRad = m_KeyFovRad.Get(0);
			focusM = m_KeyFocus.Get(0);
			EnsureActiveCam(pos, ypr, fovRad);
			ApplyCamFocus(focusM, DSBX_Const.CAM_FOCUS_BLUR);
			return;
		}
		if (tMs >= m_KeyT.Get(n - 1))
		{
			pos = m_KeyPos.Get(n - 1);
			ypr = m_KeyYpr.Get(n - 1);
			fovRad = m_KeyFovRad.Get(n - 1);
			focusM = m_KeyFocus.Get(n - 1);
			EnsureActiveCam(pos, ypr, fovRad);
			ApplyCamFocus(focusM, DSBX_Const.CAM_FOCUS_BLUR);
			return;
		}
		int k = 0;
		while (k < n - 1 && !(m_KeyT.Get(k) <= tMs && tMs < m_KeyT.Get(k + 1)))
		{
			k = k + 1;
		}
		float t0 = m_KeyT.Get(k);
		float t1 = m_KeyT.Get(k + 1);
		float span = t1 - t0;
		float u = 0.0;
		if (span > 0.0)
		{
			u = (tMs - t0) / span;
		}
		vector p1 = m_KeyPos.Get(k);
		vector p2 = m_KeyPos.Get(k + 1);
		if (n == 2)
		{
			pos = p1 + (p2 - p1) * u;
		}
		else
		{
			vector p0 = p1;
			if (k > 0)
			{
				p0 = m_KeyPos.Get(k - 1);
			}
			vector p3 = p2;
			if (k + 2 < n)
			{
				p3 = m_KeyPos.Get(k + 2);
			}
			pos = CatmullPos(p0, p1, p2, p3, u);
		}
		float qa[4];
		float qb[4];
		qa[0] = m_KeyQ0.Get(k);
		qa[1] = m_KeyQ1.Get(k);
		qa[2] = m_KeyQ2.Get(k);
		qa[3] = m_KeyQ3.Get(k);
		qb[0] = m_KeyQ0.Get(k + 1);
		qb[1] = m_KeyQ1.Get(k + 1);
		qb[2] = m_KeyQ2.Get(k + 1);
		qb[3] = m_KeyQ3.Get(k + 1);
		float qout[4];
		SlerpQuat(qa, qb, u, qout);
		vector rot[3];
		Math3D.QuatToMatrix(qout, rot);
		vector mat4[4];
		CopyRotToMat4(rot, pos, mat4);
		fovRad = m_KeyFovRad.Get(k) + (m_KeyFovRad.Get(k + 1) - m_KeyFovRad.Get(k)) * u;
		focusM = m_KeyFocus.Get(k) + (m_KeyFocus.Get(k + 1) - m_KeyFocus.Get(k)) * u;
		if (!g_Game)
		{
			return;
		}
		if (!m_Cam)
		{
			m_Cam = Camera.Cast(g_Game.CreateObject("staticcamera", pos, true));
		}
		if (!m_Cam)
		{
			return;
		}
		m_Cam.SetTransform(mat4);
		m_Cam.SetFOV(fovRad);
		m_Cam.SetActive(true);
		ApplyCamFocus(focusM, DSBX_Const.CAM_FOCUS_BLUR);
	}
}
