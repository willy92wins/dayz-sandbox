class DSBX_QA_CamPose : Managed
{
	vector m_Pos;
	vector m_Ypr;
	float m_FovRad;

	void DSBX_QA_CamPose()
	{
		m_Pos = "0 0 0";
		m_Ypr = "0 0 0";
		m_FovRad = 0.7;
	}
}

class DSBX_QA_CamKey : Managed
{
	float m_TS;
	vector m_Pos;
	vector m_Ypr;
	float m_FovRad;
	float m_FocusDistM;
	float m_FocusBlur;
	float m_Q0;
	float m_Q1;
	float m_Q2;
	float m_Q3;

	void DSBX_QA_CamKey()
	{
		m_TS = 0.0;
		m_Pos = "0 0 0";
		m_Ypr = "0 0 0";
		m_FovRad = 0.7;
		m_FocusDistM = 0.0;
		m_FocusBlur = 0.0;
		m_Q0 = 0.0;
		m_Q1 = 0.0;
		m_Q2 = 0.0;
		m_Q3 = 1.0;
	}
}

class DSBX_QA_X_Cam : DSBX_QA_Ext
{
	Camera m_Cam;
	Camera m_CamTarget;
	bool m_FreeCamActive;
	vector m_FreePos;
	float m_FreeYawDeg;
	float m_FreePitchDeg;
	float m_FreeRollDeg;
	float m_FreeFovRad;
	float m_FreeSpeedMps;
	float m_FreeAngSpeedDegps;
	int m_SpeedStepsN;
	int m_FreeInputFrames;
	float m_FreeIntegratedDtS;
	int m_InputAckSeqN;

	float m_FocusEnabledB;
	float m_SentFocusDistM;
	float m_SentFocusBlur;
	int m_SetFocusCallsN;

	string m_ActiveCamJobId;
	string m_ActiveSampleJobId;
	string m_PathFault;
	string m_PathPosMode;
	string m_PathInterpMode;
	bool m_HudHiddenByJob;
	bool m_HudHidden;
	int m_SavedHudFlagsMask;
	int m_SavedAuxVisMask;
	int m_PathSeq;
	float m_PathDtSumMs;
	float m_PathDurationS;
	float m_PathTargetDurationMs;
	bool m_JumpInjected;
	bool m_FaultHudForced;
	bool m_EngineInterpSwitched;
	bool m_PathHold;
	bool m_PathRow0Emitted;
	int m_PathEmitFrame;
	bool m_SlowStopPending;
	float m_SlowStopRemainingMs;

	int m_SampleSeq;
	float m_SampleDtSumMs;
	float m_SampleDurationMs;

	ref map<string, ref DSBX_QA_CamPose> m_SavedPoses;
	ref array<string> m_SavedPoseOrder;
	ref array<Object> m_FixtureEntities;
	ref array<ref DSBX_QA_CamKey> m_PathKeys;
	ref array<vector> m_KeyPoints;
	ref array<string> m_PathNcol;
	ref array<string> m_SampleNcol;
	ref array<string> m_NoScol;
	ref array<string> m_AuxWidgetNames;
	ref array<string> m_HudElementNames;
	ref map<Widget, bool> m_BaselineWidgetVis;
	ref map<Widget, bool> m_HudKnownWidgets;
	Widget m_TestOverlay;

	void DSBX_QA_X_Cam()
	{
		m_Cam = null;
		m_CamTarget = null;
		m_FreeCamActive = false;
		m_FreePos = "0 0 0";
		m_FreeYawDeg = 0.0;
		m_FreePitchDeg = 0.0;
		m_FreeRollDeg = 0.0;
		m_FreeFovRad = 0.7;
		m_FreeSpeedMps = 4.0;
		m_FreeAngSpeedDegps = 90.0;
		m_SpeedStepsN = 0;
		m_FreeInputFrames = 0;
		m_FreeIntegratedDtS = 0.0;
		m_InputAckSeqN = 0;

		m_FocusEnabledB = 0.0;
		m_SentFocusDistM = 0.0;
		m_SentFocusBlur = 0.0;
		m_SetFocusCallsN = 0;

		m_ActiveCamJobId = "";
		m_ActiveSampleJobId = "";
		m_PathFault = "";
		m_PathPosMode = "linear";
		m_PathInterpMode = "scripted";
		m_HudHiddenByJob = false;
		m_HudHidden = false;
		m_SavedHudFlagsMask = 0;
		m_SavedAuxVisMask = 0;
		m_PathSeq = 0;
		m_PathDtSumMs = 0.0;
		m_PathDurationS = 0.0;
		m_PathTargetDurationMs = 0.0;
		m_JumpInjected = false;
		m_FaultHudForced = false;
		m_EngineInterpSwitched = false;
		m_PathHold = false;
		m_PathRow0Emitted = false;
		m_PathEmitFrame = 0;
		m_SlowStopPending = false;
		m_SlowStopRemainingMs = 0.0;

		m_SampleSeq = 0;
		m_SampleDtSumMs = 0.0;
		m_SampleDurationMs = 0.0;

		m_SavedPoses = new map<string, ref DSBX_QA_CamPose>();
		m_SavedPoseOrder = new array<string>();
		m_FixtureEntities = new array<Object>();
		m_PathKeys = new array<ref DSBX_QA_CamKey>();
		m_KeyPoints = new array<vector>();
		m_NoScol = new array<string>();
		m_BaselineWidgetVis = new map<Widget, bool>();
		m_HudKnownWidgets = new map<Widget, bool>();
		m_TestOverlay = null;

		m_PathNcol = new array<string>();
		m_PathNcol.Insert("seq_n");
		m_PathNcol.Insert("frame");
		m_PathNcol.Insert("tick_ms");
		m_PathNcol.Insert("dtsum_ms");
		m_PathNcol.Insert("x_m");
		m_PathNcol.Insert("y_m");
		m_PathNcol.Insert("z_m");
		m_PathNcol.Insert("yaw_deg");
		m_PathNcol.Insert("pitch_deg");
		m_PathNcol.Insert("roll_deg");
		m_PathNcol.Insert("eng_x_m");
		m_PathNcol.Insert("eng_y_m");
		m_PathNcol.Insert("eng_z_m");
		m_PathNcol.Insert("eng_dx");
		m_PathNcol.Insert("eng_dy");
		m_PathNcol.Insert("eng_dz");
		m_PathNcol.Insert("fov_rad");
		m_PathNcol.Insert("calc_focus_dist_m");
		m_PathNcol.Insert("sent_focus_dist_m");
		m_PathNcol.Insert("sent_focus_blur");
		m_PathNcol.Insert("set_focus_calls_n");
		m_PathNcol.Insert("active_b");
		m_PathNcol.Insert("elem_vis_mask");
		m_PathNcol.Insert("flags_mask");
		m_PathNcol.Insert("qb_vis_b");
		m_PathNcol.Insert("menu_open_b");
		m_PathNcol.Insert("ovl_vis_b");
		m_PathNcol.Insert("m00");
		m_PathNcol.Insert("m01");
		m_PathNcol.Insert("m02");
		m_PathNcol.Insert("m10");
		m_PathNcol.Insert("m11");
		m_PathNcol.Insert("m12");
		m_PathNcol.Insert("m20");
		m_PathNcol.Insert("m21");
		m_PathNcol.Insert("m22");

		m_SampleNcol = new array<string>();
		m_SampleNcol.Insert("seq_n");
		m_SampleNcol.Insert("frame");
		m_SampleNcol.Insert("tick_ms");
		m_SampleNcol.Insert("dtsum_ms");
		m_SampleNcol.Insert("eng_x_m");
		m_SampleNcol.Insert("eng_y_m");
		m_SampleNcol.Insert("eng_z_m");
		m_SampleNcol.Insert("eng_dx");
		m_SampleNcol.Insert("eng_dy");
		m_SampleNcol.Insert("eng_dz");
		m_SampleNcol.Insert("fov_rad");
		m_SampleNcol.Insert("pl_cam_x_m");
		m_SampleNcol.Insert("pl_cam_y_m");
		m_SampleNcol.Insert("pl_cam_z_m");
		m_SampleNcol.Insert("pl_cam_dx");
		m_SampleNcol.Insert("pl_cam_dy");
		m_SampleNcol.Insert("pl_cam_dz");
		m_SampleNcol.Insert("mcam_active_b");

		m_AuxWidgetNames = new array<string>();
		m_AuxWidgetNames.Insert("CursorIcons");
		m_AuxWidgetNames.Insert("PermanentCrossHair");
		m_AuxWidgetNames.Insert("WalkieTalkie");
		m_AuxWidgetNames.Insert("ActionTargetsCursorWidget");
		m_AuxWidgetNames.Insert("StaminaBar");
		m_AuxWidgetNames.Insert("StaminaBackground");
		m_AuxWidgetNames.Insert("GameStatusIcons");

		m_HudElementNames = new array<string>();
		m_HudElementNames.Insert("PresencePanel");
		m_HudElementNames.Insert("StancePanel");
		m_HudElementNames.Insert("PlayerPanel");
		m_HudElementNames.Insert("VehicleHUDPanels");
		m_HudElementNames.Insert("BadgesPanel");
		m_HudElementNames.Insert("BadgeNotifierDivider");
		m_HudElementNames.Insert("NotifiersPanel");
		m_HudElementNames.Insert("QuickbarGrid");
	}

	override void Init(DSBX_QA_Probe probe)
	{
		super.Init(probe);
		m_ActiveCamJobId = "";
		m_ActiveSampleJobId = "";
		m_PathFault = "";
		m_PathHold = false;
		m_SavedPoses.Clear();
		m_SavedPoseOrder.Clear();
		m_FixtureEntities.Clear();
		m_BaselineWidgetVis.Clear();
		m_HudKnownWidgets.Clear();
		m_SpeedStepsN = 0;
		m_FreeInputFrames = 0;
		m_FreeIntegratedDtS = 0.0;
		m_InputAckSeqN = 0;
		m_SetFocusCallsN = 0;
	}

	override bool Handles(string verb, string role)
	{
		if (role != "client")
		{
			return false;
		}
		if (verb == "scam_fixture_setup" || verb == "scam_state_read" || verb == "scam_free_op" || verb == "scam_pose_save" || verb == "scam_pose_apply" || verb == "scam_path_start" || verb == "scam_dof_set" || verb == "scam_hud_op" || verb == "scam_sample_start")
		{
			return true;
		}
		return false;
	}

	bool GetStr(DSBX_QA_Args args, string key, out string value)
	{
		value = "";
		int i = 0;
		while (i < args.sk.Count())
		{
			if (args.sk.Get(i) == key)
			{
				value = args.sv.Get(i);
				return true;
			}
			i = i + 1;
		}
		return false;
	}

	bool GetNum(DSBX_QA_Args args, string key, out float value)
	{
		value = 0.0;
		int i = 0;
		while (i < args.nk.Count())
		{
			if (args.nk.Get(i) == key)
			{
				value = args.nv.Get(i);
				return true;
			}
			i = i + 1;
		}
		return false;
	}

	void Reject(DSBX_QA_Result res, string reason)
	{
		res.status = "rejected";
		res.reason = reason;
	}

	void FailLease(DSBX_QA_Result res)
	{
		res.status = "error";
		res.reason = "lease_expired";
	}

	void CopyRotToMat4(vector rot[3], vector pos, out vector mat4[4])
	{
		mat4[0] = rot[0];
		mat4[1] = rot[1];
		mat4[2] = rot[2];
		mat4[3] = pos;
	}

	void ExtractRotFromMat4(vector mat4[4], out vector rot[3])
	{
		rot[0] = mat4[0];
		rot[1] = mat4[1];
		rot[2] = mat4[2];
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

	bool EnsureActiveCam(vector pos, vector yprDeg, float fovRad, string fault)
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
		if (fault == "cam_no_activate")
		{
			m_Cam.SetActive(false);
		}
		else
		{
			m_Cam.SetActive(true);
		}
		return true;
	}

	void ApplyCamFocus(float distM, float blur)
	{
		if (m_Cam)
		{
			m_Cam.SetFocus(distM, blur);
		}
		m_SentFocusDistM = distM;
		m_SentFocusBlur = blur;
		m_SetFocusCallsN = m_SetFocusCallsN + 1;
	}

	void DestroyCameras()
	{
		if (m_Cam)
		{
			m_Cam.StopInterpolation();
			ApplyCamFocus(0.0, 0.0);
			m_FocusEnabledB = 0.0;
			m_Cam.SetActive(false);
			if (g_Game)
			{
				g_Game.ObjectDelete(m_Cam);
			}
			m_Cam = null;
		}
		if (m_CamTarget)
		{
			m_CamTarget.StopInterpolation();
			m_CamTarget.SetActive(false);
			if (g_Game)
			{
				g_Game.ObjectDelete(m_CamTarget);
			}
			m_CamTarget = null;
		}
	}

	void DestroyCamerasPreserveFocus()
	{
		if (m_Cam)
		{
			m_Cam.StopInterpolation();
			m_Cam.SetActive(false);
			if (g_Game)
			{
				g_Game.ObjectDelete(m_Cam);
			}
			m_Cam = null;
		}
		if (m_CamTarget)
		{
			m_CamTarget.StopInterpolation();
			m_CamTarget.SetActive(false);
			if (g_Game)
			{
				g_Game.ObjectDelete(m_CamTarget);
			}
			m_CamTarget = null;
		}
	}

	void CleanupFixtureEntities()
	{
		int i = 0;
		while (i < m_FixtureEntities.Count())
		{
			Object ent = m_FixtureEntities.Get(i);
			if (ent && g_Game)
			{
				g_Game.ObjectDelete(ent);
			}
			i = i + 1;
		}
		m_FixtureEntities.Clear();
	}

	string SavedNamesCsv()
	{
		string outCsv = "";
		int i = 0;
		while (i < m_SavedPoseOrder.Count())
		{
			if (i > 0)
			{
				outCsv = outCsv + ",";
			}
			outCsv = outCsv + m_SavedPoseOrder.Get(i);
			i = i + 1;
		}
		return outCsv;
	}

	void StoreSavedPose(string name, vector pos, vector ypr, float fovRad)
	{
		DSBX_QA_CamPose pose = new DSBX_QA_CamPose();
		pose.m_Pos = pos;
		pose.m_Ypr = ypr;
		pose.m_FovRad = fovRad;
		if (!m_SavedPoses.Contains(name))
		{
			m_SavedPoseOrder.Insert(name);
		}
		m_SavedPoses.Set(name, pose);
	}

	int ReadElemVisMask()
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
		if (vis.IsElementVisible(EHudElement.LHUD_PRESENCE))
		{
			mask = mask | 1;
		}
		if (vis.IsElementVisible(EHudElement.LHUD_STANCE))
		{
			mask = mask | 2;
		}
		if (vis.IsElementVisible(EHudElement.LHUD_PLAYER))
		{
			mask = mask | 4;
		}
		if (vis.IsElementVisible(EHudElement.LHUD_VEHICLE))
		{
			mask = mask | 8;
		}
		if (vis.IsElementVisible(EHudElement.RHUD_BADGES))
		{
			mask = mask | 16;
		}
		if (vis.IsElementVisible(EHudElement.RHUD_DIVIDER))
		{
			mask = mask | 32;
		}
		if (vis.IsElementVisible(EHudElement.RHUD_NOTIFIERS))
		{
			mask = mask | 64;
		}
		if (vis.IsElementVisible(EHudElement.QUICKBAR))
		{
			mask = mask | 128;
		}
		return mask;
	}

	float ReadQuickbarVisB()
	{
		IngameHud hud = GetIngameHud();
		if (!hud)
		{
			return 0.0;
		}
		IngameHudVisibility vis = hud.GetHudVisibility();
		if (!vis)
		{
			return 0.0;
		}
		if (vis.IsElementVisible(EHudElement.QUICKBAR))
		{
			return 1.0;
		}
		return 0.0;
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

	int CountQuickbarItems(PlayerBase player)
	{
		if (!player)
		{
			return 0;
		}
		int count = 0;
		int sz = player.GetQuickBarSize();
		int qi = 0;
		while (qi < sz)
		{
			if (player.GetQuickBarEntity(qi) != null)
			{
				count = count + 1;
			}
			qi = qi + 1;
		}
		return count;
	}

	float ReadMenuOpenB()
	{
		if (!g_Game)
		{
			return 0.0;
		}
		UIManager uim = g_Game.GetUIManager();
		if (uim && uim.GetMenu() != null)
		{
			return 1.0;
		}
		return 0.0;
	}

	void RecordBaselineSubtree(Widget node)
	{
		Widget cur = node;
		while (cur)
		{
			m_BaselineWidgetVis.Set(cur, cur.IsVisible());
			Widget child = cur.GetChildren();
			if (child)
			{
				RecordBaselineSubtree(child);
			}
			cur = cur.GetSibling();
		}
	}

	void RecordBaselineWidgetTree()
	{
		m_BaselineWidgetVis.Clear();
		m_HudKnownWidgets.Clear();
		if (!g_Game)
		{
			return;
		}
		WorkspaceWidget ws = g_Game.GetWorkspace();
		if (ws)
		{
			RecordBaselineSubtree(ws.GetChildren());
		}
		IngameHud hud = GetIngameHud();
		if (hud)
		{
			Widget panel = hud.GetHudPanelWidget();
			if (panel)
			{
				int i = 0;
				while (i < m_HudElementNames.Count())
				{
					Widget ew = panel.FindAnyWidget(m_HudElementNames.Get(i));
					if (ew)
					{
						m_HudKnownWidgets.Set(ew, true);
					}
					i = i + 1;
				}
				int j = 0;
				while (j < m_AuxWidgetNames.Count())
				{
					Widget aw = panel.FindAnyWidget(m_AuxWidgetNames.Get(j));
					if (aw)
					{
						m_HudKnownWidgets.Set(aw, true);
					}
					j = j + 1;
				}
			}
		}
	}

	bool ScanOverlaySubtree(Widget node)
	{
		Widget cur = node;
		while (cur)
		{
			if (cur.IsVisibleHierarchy())
			{
				if (!m_BaselineWidgetVis.Contains(cur))
				{
					return true;
				}
				bool baseVis = m_BaselineWidgetVis.Get(cur);
				if (!baseVis && cur.IsVisible())
				{
					if (m_HudHidden || !m_HudKnownWidgets.Contains(cur))
					{
						return true;
					}
				}
			}
			Widget child = cur.GetChildren();
			if (child)
			{
				if (ScanOverlaySubtree(child))
				{
					return true;
				}
			}
			cur = cur.GetSibling();
		}
		return false;
	}

	float ScanOverlayTree()
	{
		if (m_TestOverlay && m_TestOverlay.IsVisibleHierarchy())
		{
			return 1.0;
		}
		if (m_HudHidden)
		{
			IngameHud hud = GetIngameHud();
			if (hud)
			{
				Widget panel = hud.GetHudPanelWidget();
				if (panel)
				{
					int i = 0;
					while (i < m_AuxWidgetNames.Count())
					{
						Widget aw = panel.FindAnyWidget(m_AuxWidgetNames.Get(i));
						if (aw && aw.IsVisibleHierarchy())
						{
							return 1.0;
						}
						i = i + 1;
					}
				}
			}
		}
		if (m_BaselineWidgetVis.Count() > 0 && g_Game)
		{
			WorkspaceWidget ws = g_Game.GetWorkspace();
			if (ws)
			{
				if (ScanOverlaySubtree(ws.GetChildren()))
				{
					return 1.0;
				}
			}
		}
		return 0.0;
	}

	void DestroyTestOverlay()
	{
		if (m_TestOverlay)
		{
			m_TestOverlay.Unlink();
			m_TestOverlay = null;
		}
	}

	void CreateTestOverlay()
	{
		DestroyTestOverlay();
		if (!g_Game)
		{
			return;
		}
		WorkspaceWidget ws = g_Game.GetWorkspace();
		IngameHud hud = GetIngameHud();
		Widget parentW = null;
		if (hud)
		{
			parentW = hud.GetHudPanelWidget();
		}
		if (ws)
		{
			m_TestOverlay = ws.CreateWidget(FrameWidgetTypeID, 32, 32, 24, 24, WidgetFlags.VISIBLE, 0xCCFF0000, 999, parentW);
		}
	}

	void HideHudAndSaveState()
	{
		m_SavedHudFlagsMask = ReadHudFlagsMask();
		m_SavedAuxVisMask = ReadAuxVisMask();
		m_HudHidden = true;
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
		DestroyTestOverlay();
		ApplyHudFlagsMask(m_SavedHudFlagsMask);
		ApplyAuxVisMask(m_SavedAuxVisMask);
		m_HudHidden = false;
	}

	void ForceQuickbarVisible()
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
		vis.SetContextFlag(EHudContextFlags.QUICKBAR_HIDE, false);
		vis.SetContextFlag(EHudContextFlags.QUICKBAR_DISABLE, false);
		vis.SetContextFlag(EHudContextFlags.QUICKBAR_GLOBAL, false);
	}

	void ForceQuickbarAndOverlay()
	{
		ForceQuickbarVisible();
		CreateTestOverlay();
	}

	void ReadCamNodeState(Camera cam, out float activeB, out vector pos, out vector ypr, out vector rot[3])
	{
		activeB = 0.0;
		pos = "0 0 0";
		ypr = "0 0 0";
		rot[0] = "1 0 0";
		rot[1] = "0 1 0";
		rot[2] = "0 0 1";
		if (!cam)
		{
			return;
		}
		if (cam.IsActive())
		{
			activeB = 1.0;
		}
		vector mat4[4];
		cam.GetTransform(mat4);
		ExtractRotFromMat4(mat4, rot);
		pos = mat4[3];
		ypr = Math3D.MatrixToAngles(rot);
	}

	void AddNk(DSBX_QA_Read read, string k, float v)
	{
		read.nk.Insert(k);
		read.nv.Insert(v);
	}

	void AddSk(DSBX_QA_Read read, string k, string v)
	{
		read.sk.Insert(k);
		read.sv.Insert(v);
	}

	bool IsCamJobRunning()
	{
		if (m_ActiveCamJobId == "" || !m_Jobs)
		{
			return false;
		}
		return m_Jobs.GetState(m_ActiveCamJobId) == "running";
	}

	override void OnStartOp(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string verb = op.verb;
		if (verb != "scam_path_start")
		{
			m_PathHold = false;
		}
		string fault = m_Probe.GetOpFault();
		PlayerBase player = null;
		if (g_Game)
		{
			player = PlayerBase.Cast(g_Game.GetPlayer());
		}
		if (!player || fault == "cam_no_player")
		{
			Reject(res, "client_not_in_game");
			return;
		}
		if (verb == "scam_state_read")
		{
			DoStateRead(player, res);
			return;
		}
		if (verb == "scam_fixture_setup")
		{
			DoFixtureSetup(player, args, fault, res);
			return;
		}
		if (verb == "scam_free_op")
		{
			DoFreeOp(args, fault, res);
			return;
		}
		if (verb == "scam_pose_save")
		{
			DoPoseSave(args, res);
			return;
		}
		if (verb == "scam_pose_apply")
		{
			DoPoseApply(args, fault, res);
			return;
		}
		if (verb == "scam_path_start")
		{
			DoPathStart(op, args, fault, res);
			return;
		}
		if (verb == "scam_dof_set")
		{
			DoDofSet(args, fault, res);
			return;
		}
		if (verb == "scam_hud_op")
		{
			DoHudOp(player, args, res);
			return;
		}
		if (verb == "scam_sample_start")
		{
			DoSampleStart(op, player, args, res);
			return;
		}
		Reject(res, "unknown_verb");
	}

	void DoFixtureSetup(PlayerBase player, DSBX_QA_Args args, string fault, DSBX_QA_Result res)
	{
		if (!m_Probe.LeaseOk())
		{
			FailLease(res);
			return;
		}
		float anchorX;
		float anchorZ;
		float anchorEyeH;
		float anchorYaw;
		float anchorPitch;
		float anchorRoll;
		float anchorFov;
		float subjDist;
		float bgDist;
		if (!GetNum(args, "anchor_x_m", anchorX) || !GetNum(args, "anchor_z_m", anchorZ) || !GetNum(args, "anchor_eye_h_m", anchorEyeH) || !GetNum(args, "anchor_yaw_deg", anchorYaw) || !GetNum(args, "anchor_pitch_deg", anchorPitch) || !GetNum(args, "anchor_roll_deg", anchorRoll) || !GetNum(args, "anchor_fov_rad", anchorFov) || !GetNum(args, "subj_dist_m", subjDist) || !GetNum(args, "bg_dist_m", bgDist))
		{
			Reject(res, "bad_args");
			return;
		}
		if (!m_Probe.IsFiniteF(anchorX) || !m_Probe.IsFiniteF(anchorZ) || !m_Probe.IsFiniteF(anchorEyeH) || !m_Probe.IsFiniteF(anchorYaw) || !m_Probe.IsFiniteF(anchorPitch) || !m_Probe.IsFiniteF(anchorRoll) || !m_Probe.IsFiniteF(anchorFov) || !m_Probe.IsFiniteF(subjDist) || !m_Probe.IsFiniteF(bgDist))
		{
			Reject(res, "bad_args");
			return;
		}
		if (anchorFov < 0.1 || anchorFov > 2.8 || anchorPitch < -89.0 || anchorPitch > 89.0 || anchorRoll < -180.0 || anchorRoll > 180.0 || subjDist <= 0.0 || bgDist <= 0.0)
		{
			Reject(res, "bad_args");
			return;
		}
		if (player.GetCommand_Vehicle() != null || player.GetParent() != null)
		{
			Reject(res, "player_in_vehicle");
			return;
		}
		CleanupFixtureEntities();
		float surfY = g_Game.SurfaceY(anchorX, anchorZ);
		float anchorY = surfY + anchorEyeH;
		vector anchorPos = Vector(anchorX, anchorY, anchorZ);
		vector anchorYpr = Vector(anchorYaw, anchorPitch, anchorRoll);
		float plZ = anchorZ - 4.0;
		vector plPos = Vector(anchorX, g_Game.SurfaceY(anchorX, plZ), plZ);
		player.SetPosition(plPos);

		float subjX = anchorX + 0.28;
		float subjZ = anchorZ + subjDist;
		vector subjPos = Vector(subjX, g_Game.SurfaceY(subjX, subjZ), subjZ);
		Object subjObj = g_Game.CreateObjectEx("Barrel_Red", subjPos, ECE_LOCAL);
		float subjPresentB = 0.0;
		if (subjObj)
		{
			subjObj.SetPosition(subjPos);
			m_FixtureEntities.Insert(subjObj);
			subjPresentB = 1.0;
		}

		float bgX = anchorX - 6.0;
		float bgZ = anchorZ + bgDist;
		vector bgPos = Vector(bgX, g_Game.SurfaceY(bgX, bgZ), bgZ);
		Object bgObj = g_Game.CreateObjectEx("Land_Mil_Barracks1", bgPos, ECE_LOCAL);
		float bgPresentB = 0.0;
		if (bgObj)
		{
			bgObj.SetPosition(bgPos);
			m_FixtureEntities.Insert(bgObj);
			bgPresentB = 1.0;
		}

		int qbItems = CountQuickbarItems(player);
		if (qbItems == 0)
		{
			array<EntityAI> items = new array<EntityAI>();
			GameInventory inv = player.GetInventory();
			if (inv)
			{
				inv.EnumerateInventory(InventoryTraversalType.PREORDER, items);
				int ii = 0;
				while (ii < items.Count())
				{
					EntityAI it = items.Get(ii);
					if (it && it != player)
					{
						player.SetQuickBarEntityShortcut(it, 0, true);
						break;
					}
					ii = ii + 1;
				}
			}
			qbItems = CountQuickbarItems(player);
		}

		RecordBaselineWidgetTree();
		if (!EnsureActiveCam(anchorPos, anchorYpr, anchorFov, fault))
		{
			res.status = "error";
			res.reason = "camera_create_failed";
			return;
		}
		ApplyCamFocus(0.0, 0.0);
		m_FocusEnabledB = 0.0;
		m_FreeCamActive = false;
		m_FreePos = anchorPos;
		m_FreeYawDeg = anchorYaw;
		m_FreePitchDeg = anchorPitch;
		m_FreeRollDeg = anchorRoll;
		m_FreeFovRad = anchorFov;

		float activeB = 0.0;
		if (m_Cam && m_Cam.IsActive())
		{
			activeB = 1.0;
		}
		res.status = "done";
		res.reason = "";
		res.read.has.Insert("payload");
		AddNk(res.read, "frame", m_Probe.m_Frame);
		AddNk(res.read, "tick_ms", m_Probe.NowMs());
		AddNk(res.read, "active_b", activeB);
		AddNk(res.read, "anchor_x_m", anchorX);
		AddNk(res.read, "anchor_y_m", anchorY);
		AddNk(res.read, "anchor_z_m", anchorZ);
		AddNk(res.read, "subj_present_b", subjPresentB);
		AddNk(res.read, "subj_dist_m", subjDist);
		AddNk(res.read, "bg_present_b", bgPresentB);
		AddNk(res.read, "bg_dist_m", bgDist);
		AddNk(res.read, "qb_items_n", qbItems);
		AddNk(res.read, "player_in_veh_b", 0.0);
	}

	void DoStateRead(PlayerBase player, DSBX_QA_Result res)
	{
		float activeB;
		vector pos;
		vector ypr;
		vector rot[3];
		Camera nodeCam = m_Cam;
		if (m_ActiveCamJobId != "" && m_PathInterpMode == "engine_interp" && m_EngineInterpSwitched && m_CamTarget)
		{
			nodeCam = m_CamTarget;
		}
		ReadCamNodeState(nodeCam, activeB, pos, ypr, rot);
		vector engPos = g_Game.GetCurrentCameraPosition();
		vector engDir = g_Game.GetCurrentCameraDirection();
		float fovRad = Camera.GetCurrentFOV();

		string camState = "";
		if (m_ActiveCamJobId != "" && m_Jobs)
		{
			camState = m_Jobs.GetState(m_ActiveCamJobId);
		}
		string sampleState = "";
		if (m_ActiveSampleJobId != "" && m_Jobs)
		{
			sampleState = m_Jobs.GetState(m_ActiveSampleJobId);
		}

		res.status = "done";
		res.reason = "";
		res.read.has.Insert("payload");
		AddSk(res.read, "cam_job_id", m_ActiveCamJobId);
		AddSk(res.read, "cam_job_state", camState);
		AddSk(res.read, "sample_job_id", m_ActiveSampleJobId);
		AddSk(res.read, "sample_job_state", sampleState);
		AddSk(res.read, "saved_names_csv", SavedNamesCsv());

		AddNk(res.read, "frame", m_Probe.m_Frame);
		AddNk(res.read, "tick_ms", m_Probe.NowMs());
		AddNk(res.read, "cam_dtsum_ms", m_PathDtSumMs);
		AddNk(res.read, "active_b", activeB);
		AddNk(res.read, "enable_b", m_FocusEnabledB);
		AddNk(res.read, "sent_focus_dist_m", m_SentFocusDistM);
		AddNk(res.read, "sent_focus_blur", m_SentFocusBlur);
		AddNk(res.read, "set_focus_calls_n", m_SetFocusCallsN);
		AddNk(res.read, "saved_count_n", m_SavedPoses.Count());
		AddNk(res.read, "speed_mps", m_FreeSpeedMps);
		AddNk(res.read, "speed_steps_n", m_SpeedStepsN);
		AddNk(res.read, "input_frames_n", m_FreeInputFrames);
		AddNk(res.read, "integrated_dt_s", m_FreeIntegratedDtS);
		AddNk(res.read, "input_ack_seq_n", m_InputAckSeqN);
		AddNk(res.read, "x_m", pos[0]);
		AddNk(res.read, "y_m", pos[1]);
		AddNk(res.read, "z_m", pos[2]);
		AddNk(res.read, "yaw_deg", ypr[0]);
		AddNk(res.read, "pitch_deg", ypr[1]);
		AddNk(res.read, "roll_deg", ypr[2]);
		AddNk(res.read, "fov_rad", fovRad);
		AddNk(res.read, "m00", rot[0][0]);
		AddNk(res.read, "m01", rot[0][1]);
		AddNk(res.read, "m02", rot[0][2]);
		AddNk(res.read, "m10", rot[1][0]);
		AddNk(res.read, "m11", rot[1][1]);
		AddNk(res.read, "m12", rot[1][2]);
		AddNk(res.read, "m20", rot[2][0]);
		AddNk(res.read, "m21", rot[2][1]);
		AddNk(res.read, "m22", rot[2][2]);
		AddNk(res.read, "eng_x_m", engPos[0]);
		AddNk(res.read, "eng_y_m", engPos[1]);
		AddNk(res.read, "eng_z_m", engPos[2]);
		AddNk(res.read, "eng_dx", engDir[0]);
		AddNk(res.read, "eng_dy", engDir[1]);
		AddNk(res.read, "eng_dz", engDir[2]);
		AddNk(res.read, "elem_vis_mask", ReadElemVisMask());
		AddNk(res.read, "flags_mask", ReadHudFlagsMask());
		AddNk(res.read, "saved_flags_mask", m_SavedHudFlagsMask);
		AddNk(res.read, "aux_vis_mask", ReadAuxVisMask());
		AddNk(res.read, "saved_aux_vis_mask", m_SavedAuxVisMask);
		AddNk(res.read, "qb_vis_b", ReadQuickbarVisB());
		AddNk(res.read, "qb_items_n", CountQuickbarItems(player));
		AddNk(res.read, "menu_open_b", ReadMenuOpenB());
		AddNk(res.read, "ovl_vis_b", ScanOverlayTree());
	}

	void DoFreeOp(DSBX_QA_Args args, string fault, DSBX_QA_Result res)
	{
		float opCodeF;
		if (!GetNum(args, "op_code", opCodeF) || !m_Probe.IsIntF(opCodeF))
		{
			Reject(res, "bad_args");
			return;
		}
		int opCode = (int)opCodeF;
		if (opCode != 1 && opCode != 3)
		{
			Reject(res, "bad_args");
			return;
		}
		if (opCode == 1)
		{
			if (!m_Probe.LeaseOk())
			{
				FailLease(res);
				return;
			}
			float xM;
			float yM;
			float zM;
			float yawDeg;
			float pitchDeg;
			float rollDeg;
			float fovRad;
			float speedMps;
			float angSpeedDegps;
			if (!GetNum(args, "x_m", xM) || !GetNum(args, "y_m", yM) || !GetNum(args, "z_m", zM) || !GetNum(args, "yaw_deg", yawDeg) || !GetNum(args, "pitch_deg", pitchDeg) || !GetNum(args, "roll_deg", rollDeg) || !GetNum(args, "fov_rad", fovRad) || !GetNum(args, "speed_mps", speedMps) || !GetNum(args, "ang_speed_degps", angSpeedDegps))
			{
				Reject(res, "bad_args");
				return;
			}
			if (!m_Probe.IsFiniteF(xM) || !m_Probe.IsFiniteF(yM) || !m_Probe.IsFiniteF(zM) || !m_Probe.IsFiniteF(yawDeg) || !m_Probe.IsFiniteF(pitchDeg) || !m_Probe.IsFiniteF(rollDeg) || !m_Probe.IsFiniteF(fovRad) || !m_Probe.IsFiniteF(speedMps) || !m_Probe.IsFiniteF(angSpeedDegps))
			{
				Reject(res, "bad_args");
				return;
			}
			if (fovRad < 0.1 || fovRad > 2.8 || speedMps <= 0.0 || speedMps > 100.0 || angSpeedDegps <= 0.0 || pitchDeg < -89.0 || pitchDeg > 89.0 || rollDeg < -180.0 || rollDeg > 180.0)
			{
				Reject(res, "bad_args");
				return;
			}
			if (IsCamJobRunning())
			{
				Reject(res, "busy");
				return;
			}
			vector pos = Vector(xM, yM, zM);
			vector ypr = Vector(yawDeg, pitchDeg, rollDeg);
			SetPlayerControlDisabled(true);
			if (!EnsureActiveCam(pos, ypr, fovRad, fault))
			{
				SetPlayerControlDisabled(false);
				res.status = "error";
				res.reason = "camera_create_failed";
				return;
			}
			ApplyCamFocus(0.0, 0.0);
			m_FocusEnabledB = 0.0;
			m_FreeCamActive = true;
			m_FreePos = pos;
			m_FreeYawDeg = yawDeg;
			m_FreePitchDeg = pitchDeg;
			m_FreeRollDeg = rollDeg;
			m_FreeFovRad = fovRad;
			m_FreeSpeedMps = speedMps;
			m_FreeAngSpeedDegps = angSpeedDegps;
			m_FreeInputFrames = 0;
			m_FreeIntegratedDtS = 0.0;
			m_SpeedStepsN = 0;
		}
		else
		{
			m_FreeCamActive = false;
			DestroyCameras();
			SetPlayerControlDisabled(false);
		}
		float activeB;
		vector outPos;
		vector outYpr;
		vector outRot[3];
		ReadCamNodeState(m_Cam, activeB, outPos, outYpr, outRot);
		vector engPos = g_Game.GetCurrentCameraPosition();
		vector engDir = g_Game.GetCurrentCameraDirection();
		float outFov = Camera.GetCurrentFOV();

		res.status = "done";
		res.reason = "";
		res.read.has.Insert("payload");
		AddNk(res.read, "frame", m_Probe.m_Frame);
		AddNk(res.read, "tick_ms", m_Probe.NowMs());
		AddNk(res.read, "active_b", activeB);
		AddNk(res.read, "x_m", outPos[0]);
		AddNk(res.read, "y_m", outPos[1]);
		AddNk(res.read, "z_m", outPos[2]);
		AddNk(res.read, "yaw_deg", outYpr[0]);
		AddNk(res.read, "pitch_deg", outYpr[1]);
		AddNk(res.read, "roll_deg", outYpr[2]);
		AddNk(res.read, "fov_rad", outFov);
		AddNk(res.read, "speed_mps", m_FreeSpeedMps);
		AddNk(res.read, "speed_steps_n", m_SpeedStepsN);
		AddNk(res.read, "eng_x_m", engPos[0]);
		AddNk(res.read, "eng_y_m", engPos[1]);
		AddNk(res.read, "eng_z_m", engPos[2]);
		AddNk(res.read, "eng_dx", engDir[0]);
		AddNk(res.read, "eng_dy", engDir[1]);
		AddNk(res.read, "eng_dz", engDir[2]);
		AddNk(res.read, "input_frames_n", m_FreeInputFrames);
		AddNk(res.read, "integrated_dt_s", m_FreeIntegratedDtS);
		AddNk(res.read, "input_ack_seq_n", m_InputAckSeqN);
	}

	void DoPoseSave(DSBX_QA_Args args, DSBX_QA_Result res)
	{
		if (!m_Probe.LeaseOk())
		{
			FailLease(res);
			return;
		}
		string name;
		string overwrite;
		if (!GetStr(args, "name", name))
		{
			name = "";
		}
		if (!GetStr(args, "overwrite", overwrite))
		{
			overwrite = "0";
		}
		if (name == "")
		{
			Reject(res, "empty_name");
			return;
		}
		if (overwrite != "0" && overwrite != "1")
		{
			Reject(res, "bad_args");
			return;
		}
		if (m_SavedPoses.Contains(name) && overwrite != "1")
		{
			Reject(res, "duplicate_name");
			return;
		}
		if (!m_Cam || !m_Cam.IsActive())
		{
			Reject(res, "no_active_cam");
			return;
		}
		float activeB;
		vector pos;
		vector ypr;
		vector rot[3];
		ReadCamNodeState(m_Cam, activeB, pos, ypr, rot);
		float fovRad = Camera.GetCurrentFOV();
		StoreSavedPose(name, pos, ypr, fovRad);

		res.status = "done";
		res.reason = "";
		res.read.has.Insert("payload");
		AddSk(res.read, "name", name);
		AddSk(res.read, "saved_names_csv", SavedNamesCsv());
		AddNk(res.read, "frame", m_Probe.m_Frame);
		AddNk(res.read, "tick_ms", m_Probe.NowMs());
		AddNk(res.read, "saved_count_n", m_SavedPoses.Count());
		AddNk(res.read, "x_m", pos[0]);
		AddNk(res.read, "y_m", pos[1]);
		AddNk(res.read, "z_m", pos[2]);
		AddNk(res.read, "yaw_deg", ypr[0]);
		AddNk(res.read, "pitch_deg", ypr[1]);
		AddNk(res.read, "roll_deg", ypr[2]);
		AddNk(res.read, "fov_rad", fovRad);
	}

	void DoPoseApply(DSBX_QA_Args args, string fault, DSBX_QA_Result res)
	{
		if (!m_Probe.LeaseOk())
		{
			FailLease(res);
			return;
		}
		string name;
		if (!GetStr(args, "name", name))
		{
			name = "";
		}
		vector pos;
		vector ypr;
		float fovRad;
		if (name != "")
		{
			if (!m_Cam || (!m_Cam.IsActive() && fault != "cam_no_activate"))
			{
				Reject(res, "no_active_cam");
				return;
			}
			if (!m_SavedPoses.Contains(name))
			{
				Reject(res, "unknown_pose");
				return;
			}
			DSBX_QA_CamPose saved = m_SavedPoses.Get(name);
			pos = saved.m_Pos;
			ypr = saved.m_Ypr;
			fovRad = saved.m_FovRad;
		}
		else
		{
			float xM;
			float yM;
			float zM;
			float yawDeg;
			float pitchDeg;
			float rollDeg;
			if (!GetNum(args, "x_m", xM) || !GetNum(args, "y_m", yM) || !GetNum(args, "z_m", zM) || !GetNum(args, "yaw_deg", yawDeg) || !GetNum(args, "pitch_deg", pitchDeg) || !GetNum(args, "roll_deg", rollDeg) || !GetNum(args, "fov_rad", fovRad))
			{
				Reject(res, "bad_args");
				return;
			}
			if (!m_Probe.IsFiniteF(xM) || !m_Probe.IsFiniteF(yM) || !m_Probe.IsFiniteF(zM) || !m_Probe.IsFiniteF(yawDeg) || !m_Probe.IsFiniteF(pitchDeg) || !m_Probe.IsFiniteF(rollDeg) || !m_Probe.IsFiniteF(fovRad))
			{
				Reject(res, "bad_args");
				return;
			}
			if (fovRad < 0.1 || fovRad > 2.8 || pitchDeg < -89.0 || pitchDeg > 89.0 || rollDeg < -180.0 || rollDeg > 180.0)
			{
				Reject(res, "bad_args");
				return;
			}
			if (!m_Cam || (!m_Cam.IsActive() && fault != "cam_no_activate"))
			{
				Reject(res, "no_active_cam");
				return;
			}
			pos = Vector(xM, yM, zM);
			ypr = Vector(yawDeg, pitchDeg, rollDeg);
		}
		if (fault == "cam_no_activate")
		{
			m_Cam.SetActive(false);
		}
		if (fault == "cam_swap_axes")
		{
			float tmpY = ypr[0];
			ypr[0] = ypr[1];
			ypr[1] = tmpY;
		}
		vector rot[3];
		Math3D.YawPitchRollMatrix(ypr, rot);
		vector mat4[4];
		CopyRotToMat4(rot, pos, mat4);
		m_Cam.SetTransform(mat4);
		m_Cam.SetFOV(fovRad);
		if (m_FreeCamActive)
		{
			m_FreePos = pos;
			m_FreeYawDeg = ypr[0];
			m_FreePitchDeg = ypr[1];
			m_FreeRollDeg = ypr[2];
			m_FreeFovRad = fovRad;
		}
		float activeB;
		vector outPos;
		vector outYpr;
		vector outRot[3];
		ReadCamNodeState(m_Cam, activeB, outPos, outYpr, outRot);
		vector engPos = g_Game.GetCurrentCameraPosition();
		vector engDir = g_Game.GetCurrentCameraDirection();
		float outFov = Camera.GetCurrentFOV();

		res.status = "done";
		res.reason = "";
		res.read.has.Insert("payload");
		AddSk(res.read, "name", name);
		AddNk(res.read, "frame", m_Probe.m_Frame);
		AddNk(res.read, "tick_ms", m_Probe.NowMs());
		AddNk(res.read, "active_b", activeB);
		AddNk(res.read, "x_m", outPos[0]);
		AddNk(res.read, "y_m", outPos[1]);
		AddNk(res.read, "z_m", outPos[2]);
		AddNk(res.read, "yaw_deg", outYpr[0]);
		AddNk(res.read, "pitch_deg", outYpr[1]);
		AddNk(res.read, "roll_deg", outYpr[2]);
		AddNk(res.read, "fov_rad", outFov);
		AddNk(res.read, "m00", outRot[0][0]);
		AddNk(res.read, "m01", outRot[0][1]);
		AddNk(res.read, "m02", outRot[0][2]);
		AddNk(res.read, "m10", outRot[1][0]);
		AddNk(res.read, "m11", outRot[1][1]);
		AddNk(res.read, "m12", outRot[1][2]);
		AddNk(res.read, "m20", outRot[2][0]);
		AddNk(res.read, "m21", outRot[2][1]);
		AddNk(res.read, "m22", outRot[2][2]);
		AddNk(res.read, "eng_x_m", engPos[0]);
		AddNk(res.read, "eng_y_m", engPos[1]);
		AddNk(res.read, "eng_z_m", engPos[2]);
		AddNk(res.read, "eng_dx", engDir[0]);
		AddNk(res.read, "eng_dy", engDir[1]);
		AddNk(res.read, "eng_dz", engDir[2]);
	}

	void DoDofSet(DSBX_QA_Args args, string fault, DSBX_QA_Result res)
	{
		if (!m_Probe.LeaseOk())
		{
			FailLease(res);
			return;
		}
		float enableB;
		float focusDist;
		float focusBlur;
		if (!GetNum(args, "enable_b", enableB) || !GetNum(args, "focus_dist_m", focusDist) || !GetNum(args, "focus_blur", focusBlur))
		{
			Reject(res, "bad_args");
			return;
		}
		if (!m_Probe.IsFiniteF(enableB) || !m_Probe.IsFiniteF(focusDist) || !m_Probe.IsFiniteF(focusBlur))
		{
			Reject(res, "bad_args");
			return;
		}
		if (enableB != 0.0 && enableB != 1.0)
		{
			Reject(res, "bad_args");
			return;
		}
		if (enableB == 1.0 && (focusDist <= 0.0 || focusBlur < 0.0 || focusBlur > 1.0))
		{
			Reject(res, "bad_args");
			return;
		}
		if (enableB == 0.0 && (focusDist < 0.0 || focusBlur < 0.0 || focusBlur > 1.0))
		{
			Reject(res, "bad_args");
			return;
		}
		if (!m_Cam || !m_Cam.IsActive())
		{
			Reject(res, "no_active_cam");
			return;
		}
		if (enableB == 0.0 || fault == "cam_dof_off")
		{
			ApplyCamFocus(0.0, 0.0);
			if (enableB == 1.0)
			{
				m_FocusEnabledB = 1.0;
			}
			else
			{
				m_FocusEnabledB = 0.0;
			}
		}
		else
		{
			ApplyCamFocus(focusDist, focusBlur);
			m_FocusEnabledB = 1.0;
		}
		float activeB;
		vector outPos;
		vector outYpr;
		vector outRot[3];
		ReadCamNodeState(m_Cam, activeB, outPos, outYpr, outRot);
		float outFov = Camera.GetCurrentFOV();

		res.status = "done";
		res.reason = "";
		res.read.has.Insert("payload");
		AddNk(res.read, "frame", m_Probe.m_Frame);
		AddNk(res.read, "tick_ms", m_Probe.NowMs());
		AddNk(res.read, "active_b", activeB);
		AddNk(res.read, "enable_b", m_FocusEnabledB);
		AddNk(res.read, "sent_focus_dist_m", m_SentFocusDistM);
		AddNk(res.read, "sent_focus_blur", m_SentFocusBlur);
		AddNk(res.read, "set_focus_calls_n", m_SetFocusCallsN);
		AddNk(res.read, "x_m", outPos[0]);
		AddNk(res.read, "y_m", outPos[1]);
		AddNk(res.read, "z_m", outPos[2]);
		AddNk(res.read, "yaw_deg", outYpr[0]);
		AddNk(res.read, "pitch_deg", outYpr[1]);
		AddNk(res.read, "roll_deg", outYpr[2]);
		AddNk(res.read, "fov_rad", outFov);
	}

	void DoHudOp(PlayerBase player, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		float opCodeF;
		if (!GetNum(args, "op_code", opCodeF) || !m_Probe.IsIntF(opCodeF))
		{
			Reject(res, "bad_args");
			return;
		}
		int opCode = (int)opCodeF;
		if (opCode != 0 && opCode != 1 && opCode != 2 && opCode != 4 && opCode != 5)
		{
			Reject(res, "bad_args");
			return;
		}
		if (opCode == 1)
		{
			if (!m_Probe.LeaseOk())
			{
				FailLease(res);
				return;
			}
			HideHudAndSaveState();
		}
		else if (opCode == 2)
		{
			RestoreHudSavedState();
		}
		else if (opCode == 4)
		{
			float modeF;
			if (!GetNum(args, "mode", modeF) || !m_Probe.IsIntF(modeF))
			{
				Reject(res, "bad_args");
				return;
			}
			int mode = (int)modeF;
			if (mode < 0 || mode > 2)
			{
				Reject(res, "bad_args");
				return;
			}
			if (mode == 0)
			{
				DestroyTestOverlay();
				RestoreHudSavedState();
			}
			else
			{
				if (!m_Probe.LeaseOk())
				{
					FailLease(res);
					return;
				}
				if (mode == 1)
				{
					ForceQuickbarVisible();
				}
				else
				{
					CreateTestOverlay();
				}
			}
		}
		else if (opCode == 5)
		{
			if (!m_Probe.LeaseOk())
			{
				FailLease(res);
				return;
			}
			float presetF;
			if (!GetNum(args, "preset_mask", presetF) || !m_Probe.IsIntF(presetF))
			{
				Reject(res, "bad_args");
				return;
			}
			int presetMask = (int)presetF;
			if (presetMask < 0 || presetMask > 4095)
			{
				Reject(res, "bad_args");
				return;
			}
			DestroyTestOverlay();
			ApplyHudFlagsMask(presetMask);
			if (presetMask > 0)
			{
				int curAux = ReadAuxVisMask();
				ApplyAuxVisMask(curAux | 34);
			}
			m_SavedHudFlagsMask = presetMask;
			m_SavedAuxVisMask = ReadAuxVisMask();
			m_HudHidden = false;
		}

		float inVehB = 0.0;
		if (player.GetCommand_Vehicle() != null || player.GetParent() != null)
		{
			inVehB = 1.0;
		}
		res.status = "done";
		res.reason = "";
		res.read.has.Insert("payload");
		AddNk(res.read, "frame", m_Probe.m_Frame);
		AddNk(res.read, "tick_ms", m_Probe.NowMs());
		AddNk(res.read, "elem_vis_mask", ReadElemVisMask());
		AddNk(res.read, "flags_mask", ReadHudFlagsMask());
		AddNk(res.read, "saved_flags_mask", m_SavedHudFlagsMask);
		AddNk(res.read, "aux_vis_mask", ReadAuxVisMask());
		AddNk(res.read, "saved_aux_vis_mask", m_SavedAuxVisMask);
		AddNk(res.read, "qb_vis_b", ReadQuickbarVisB());
		AddNk(res.read, "qb_items_n", CountQuickbarItems(player));
		AddNk(res.read, "menu_open_b", ReadMenuOpenB());
		AddNk(res.read, "ovl_vis_b", ScanOverlayTree());
		AddNk(res.read, "player_in_veh_b", inVehB);
	}

	int FindColIdx(array<string> cols, string name)
	{
		int i = 0;
		while (i < cols.Count())
		{
			if (cols.Get(i) == name)
			{
				return i;
			}
			i = i + 1;
		}
		return -1;
	}

	void EmitPathRow(string jobId, int seqN, float dtsumMs, float calcFocusDist)
	{
		Camera nodeCam = m_Cam;
		if (m_PathInterpMode == "engine_interp" && m_EngineInterpSwitched && m_CamTarget)
		{
			nodeCam = m_CamTarget;
		}
		float activeB;
		vector pos;
		vector ypr;
		vector rot[3];
		ReadCamNodeState(nodeCam, activeB, pos, ypr, rot);
		vector engPos = g_Game.GetCurrentCameraPosition();
		vector engDir = g_Game.GetCurrentCameraDirection();
		float fovRad = Camera.GetCurrentFOV();

		array<float> row = new array<float>();
		row.Insert(seqN);
		row.Insert(m_Probe.m_Frame);
		row.Insert(m_Probe.NowMs());
		row.Insert(dtsumMs);
		row.Insert(pos[0]);
		row.Insert(pos[1]);
		row.Insert(pos[2]);
		row.Insert(ypr[0]);
		row.Insert(ypr[1]);
		row.Insert(ypr[2]);
		row.Insert(engPos[0]);
		row.Insert(engPos[1]);
		row.Insert(engPos[2]);
		row.Insert(engDir[0]);
		row.Insert(engDir[1]);
		row.Insert(engDir[2]);
		row.Insert(fovRad);
		row.Insert(calcFocusDist);
		row.Insert(m_SentFocusDistM);
		row.Insert(m_SentFocusBlur);
		row.Insert(m_SetFocusCallsN);
		row.Insert(activeB);
		row.Insert(ReadElemVisMask());
		row.Insert(ReadHudFlagsMask());
		row.Insert(ReadQuickbarVisB());
		row.Insert(ReadMenuOpenB());
		row.Insert(ScanOverlayTree());
		row.Insert(rot[0][0]);
		row.Insert(rot[0][1]);
		row.Insert(rot[0][2]);
		row.Insert(rot[1][0]);
		row.Insert(rot[1][1]);
		row.Insert(rot[1][2]);
		row.Insert(rot[2][0]);
		row.Insert(rot[2][1]);
		row.Insert(rot[2][2]);
		m_Jobs.AppendRow(jobId, row, m_NoScol);
	}

	void DoPathStart(DSBX_QA_Op op, DSBX_QA_Args args, string fault, DSBX_QA_Result res)
	{
		if (!m_Probe.LeaseOk())
		{
			FailLease(res);
			return;
		}
		string posMode;
		string interpMode;
		string hideHud;
		if (!GetStr(args, "pos_mode", posMode) || !GetStr(args, "interp_mode", interpMode) || !GetStr(args, "hide_hud", hideHud))
		{
			Reject(res, "bad_args");
			return;
		}
		if ((posMode != "linear" && posMode != "catmull_rom") || (interpMode != "scripted" && interpMode != "engine_interp") || (hideHud != "0" && hideHud != "1"))
		{
			Reject(res, "bad_args");
			return;
		}
		int rows = args.rows;
		int ncolN = args.ncol.Count();
		if (rows < 2 || ncolN < 10 || args.ncell.Count() != rows * ncolN)
		{
			Reject(res, "bad_args");
			return;
		}
		int cT = FindColIdx(args.ncol, "t_s");
		int cX = FindColIdx(args.ncol, "x_m");
		int cY = FindColIdx(args.ncol, "y_m");
		int cZ = FindColIdx(args.ncol, "z_m");
		int cYaw = FindColIdx(args.ncol, "yaw_deg");
		int cPitch = FindColIdx(args.ncol, "pitch_deg");
		int cRoll = FindColIdx(args.ncol, "roll_deg");
		int cFov = FindColIdx(args.ncol, "fov_rad");
		int cFdist = FindColIdx(args.ncol, "focus_dist_m");
		int cFblur = FindColIdx(args.ncol, "focus_blur");
		if (cT < 0 || cX < 0 || cY < 0 || cZ < 0 || cYaw < 0 || cPitch < 0 || cRoll < 0 || cFov < 0 || cFdist < 0 || cFblur < 0)
		{
			Reject(res, "bad_args");
			return;
		}
		array<ref DSBX_QA_CamKey> parsedKeys = new array<ref DSBX_QA_CamKey>();
		int r = 0;
		float prevT = -1.0;
		while (r < rows)
		{
			int baseIdx = r * ncolN;
			float ts = args.ncell.Get(baseIdx + cT);
			float xm = args.ncell.Get(baseIdx + cX);
			float ym = args.ncell.Get(baseIdx + cY);
			float zm = args.ncell.Get(baseIdx + cZ);
			float yaw = args.ncell.Get(baseIdx + cYaw);
			float pitch = args.ncell.Get(baseIdx + cPitch);
			float roll = args.ncell.Get(baseIdx + cRoll);
			float fov = args.ncell.Get(baseIdx + cFov);
			float fdist = args.ncell.Get(baseIdx + cFdist);
			float fblur = args.ncell.Get(baseIdx + cFblur);
			if (!m_Probe.IsFiniteF(ts) || !m_Probe.IsFiniteF(xm) || !m_Probe.IsFiniteF(ym) || !m_Probe.IsFiniteF(zm) || !m_Probe.IsFiniteF(yaw) || !m_Probe.IsFiniteF(pitch) || !m_Probe.IsFiniteF(roll) || !m_Probe.IsFiniteF(fov) || !m_Probe.IsFiniteF(fdist) || !m_Probe.IsFiniteF(fblur))
			{
				Reject(res, "bad_args");
				return;
			}
			if (r == 0 && ts != 0.0)
			{
				Reject(res, "bad_args");
				return;
			}
			if (r > 0 && ts <= prevT)
			{
				Reject(res, "bad_args");
				return;
			}
			if (fov < 0.1 || fov > 2.8 || pitch < -89.0 || pitch > 89.0 || roll < -180.0 || roll > 180.0 || fdist < 0.0 || fblur < 0.0 || fblur > 1.0)
			{
				Reject(res, "bad_args");
				return;
			}
			if (fblur > 0.0 && fdist <= 0.0)
			{
				Reject(res, "bad_args");
				return;
			}
			DSBX_QA_CamKey key = new DSBX_QA_CamKey();
			key.m_TS = ts;
			key.m_Pos = Vector(xm, ym, zm);
			key.m_Ypr = Vector(yaw, pitch, roll);
			key.m_FovRad = fov;
			key.m_FocusDistM = fdist;
			key.m_FocusBlur = fblur;
			vector kRot[3];
			Math3D.YawPitchRollMatrix(key.m_Ypr, kRot);
			float kq[4];
			Math3D.MatrixToQuat(kRot, kq);
			key.m_Q0 = kq[0];
			key.m_Q1 = kq[1];
			key.m_Q2 = kq[2];
			key.m_Q3 = kq[3];
			parsedKeys.Insert(key);
			prevT = ts;
			r = r + 1;
		}
		if (prevT <= 0.0)
		{
			Reject(res, "bad_args");
			return;
		}
		string err = m_Jobs.StartJob(this, op.op_id, "cam", m_PathNcol, m_NoScol, 3, 4096, 900000.0, "stop");
		if (err != "")
		{
			Reject(res, err);
			return;
		}
		m_PathKeys.Clear();
		m_KeyPoints.Clear();
		int ki = 0;
		while (ki < parsedKeys.Count())
		{
			DSBX_QA_CamKey pk = parsedKeys.Get(ki);
			m_PathKeys.Insert(pk);
			m_KeyPoints.Insert(pk.m_Pos);
			ki = ki + 1;
		}
		DSBX_QA_CamKey k0 = m_PathKeys.Get(0);
		if (!EnsureActiveCam(k0.m_Pos, k0.m_Ypr, k0.m_FovRad, ""))
		{
			m_Jobs.EndJob(op.op_id, "failed", "camera_create_failed");
			res.status = "error";
			res.reason = "camera_create_failed";
			return;
		}
		m_PathFault = fault;
		m_PathPosMode = posMode;
		m_PathInterpMode = interpMode;
		m_FreeCamActive = false;
		m_SlowStopPending = false;
		m_SlowStopRemainingMs = 0.0;
		m_ActiveCamJobId = op.op_id;
		m_PathSeq = 0;
		m_PathDtSumMs = 0.0;
		m_PathDurationS = prevT;
		if (m_PathFault == "cam_late_finish")
		{
			m_PathTargetDurationMs = (m_PathDurationS + 1.0) * 1000.0;
		}
		else
		{
			m_PathTargetDurationMs = m_PathDurationS * 1000.0;
		}
		m_JumpInjected = false;
		m_FaultHudForced = false;
		m_EngineInterpSwitched = false;
		m_PathHold = true;

		SetPlayerControlDisabled(true);
		if (hideHud == "1")
		{
			HideHudAndSaveState();
			m_HudHiddenByJob = true;
		}
		else
		{
			m_HudHiddenByJob = false;
		}
		ApplyCamFocus(k0.m_FocusDistM, k0.m_FocusBlur);
		if (k0.m_FocusBlur > 0.0 || k0.m_FocusDistM > 0.0)
		{
			m_FocusEnabledB = 1.0;
		}
		else
		{
			m_FocusEnabledB = 0.0;
		}
		if (interpMode == "engine_interp")
		{
			if (m_CamTarget && g_Game)
			{
				m_CamTarget.StopInterpolation();
				m_CamTarget.SetActive(false);
				g_Game.ObjectDelete(m_CamTarget);
				m_CamTarget = null;
			}
			DSBX_QA_CamKey k1 = m_PathKeys.Get(1);
			m_CamTarget = Camera.Cast(g_Game.CreateObject("staticcamera", k1.m_Pos, true));
			if (m_CamTarget)
			{
				vector rot1[3];
				Math3D.YawPitchRollMatrix(k1.m_Ypr, rot1);
				vector mat1[4];
				CopyRotToMat4(rot1, k1.m_Pos, mat1);
				m_CamTarget.SetTransform(mat1);
				m_CamTarget.SetFOV(k1.m_FovRad);
				m_CamTarget.SetFocus(k1.m_FocusDistM, k1.m_FocusBlur);
				m_CamTarget.SetActive(false);
				m_Cam.SetActive(true);
				m_Cam.EnableSmooth(false);
				Camera.InterpolateTo(m_CamTarget, k1.m_TS - k0.m_TS, 0);
			}
		}
		m_PathRow0Emitted = false;
		if (m_Probe)
		{
			m_PathEmitFrame = m_Probe.m_Frame;
		}
		m_Jobs.FillStartRead(res.read, op.op_id, "cam");
		res.status = "done";
		res.reason = "";
	}

	void EmitSampleRow(string jobId, int seqN, float dtsumMs)
	{
		vector engPos = g_Game.GetCurrentCameraPosition();
		vector engDir = g_Game.GetCurrentCameraDirection();
		float fovRad = Camera.GetCurrentFOV();
		vector plPos = "0 0 0";
		vector plDir = "0 0 1";
		vector plRot = "0 0 0";
		PlayerBase player = PlayerBase.Cast(g_Game.GetPlayer());
		if (player)
		{
			player.GetCurrentCameraTransform(plPos, plDir, plRot);
		}
		float mcamActiveB = 0.0;
		if (m_Cam && m_Cam.IsActive())
		{
			mcamActiveB = 1.0;
		}
		if (m_CamTarget && m_CamTarget.IsActive())
		{
			mcamActiveB = 1.0;
		}
		array<float> row = new array<float>();
		row.Insert(seqN);
		row.Insert(m_Probe.m_Frame);
		row.Insert(m_Probe.NowMs());
		row.Insert(dtsumMs);
		row.Insert(engPos[0]);
		row.Insert(engPos[1]);
		row.Insert(engPos[2]);
		row.Insert(engDir[0]);
		row.Insert(engDir[1]);
		row.Insert(engDir[2]);
		row.Insert(fovRad);
		row.Insert(plPos[0]);
		row.Insert(plPos[1]);
		row.Insert(plPos[2]);
		row.Insert(plDir[0]);
		row.Insert(plDir[1]);
		row.Insert(plDir[2]);
		row.Insert(mcamActiveB);
		m_Jobs.AppendRow(jobId, row, m_NoScol);
	}

	void DoSampleStart(DSBX_QA_Op op, PlayerBase player, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		if (!m_Probe.LeaseOk())
		{
			FailLease(res);
			return;
		}
		float durMs;
		if (!GetNum(args, "duration_ms", durMs) || !m_Probe.IsFiniteF(durMs))
		{
			Reject(res, "bad_args");
			return;
		}
		if (durMs < 200.0 || durMs > 10000.0)
		{
			Reject(res, "bad_args");
			return;
		}
		string err = m_Jobs.StartJob(this, op.op_id, "cam_sample", m_SampleNcol, m_NoScol, 5, 4096, 900000.0, "stop");
		if (err != "")
		{
			Reject(res, err);
			return;
		}
		m_ActiveSampleJobId = op.op_id;
		m_SampleSeq = 0;
		m_SampleDtSumMs = 0.0;
		m_SampleDurationMs = durMs;
		EmitSampleRow(m_ActiveSampleJobId, 0, 0.0);
		m_Jobs.FillStartRead(res.read, op.op_id, "cam_sample");
		res.status = "done";
		res.reason = "";
	}

	void TickFreeCam(float timeslice)
	{
		if (!m_FreeCamActive || !m_Cam || !m_Cam.IsActive() || m_ActiveCamJobId != "")
		{
			return;
		}
		if (!m_Probe.LeaseOk())
		{
			return;
		}
		if (KeyState(KeyCode.KC_PRIOR) > 0)
		{
			ClearKey(KeyCode.KC_PRIOR);
			m_FreeSpeedMps = Math.Clamp(m_FreeSpeedMps * 2.0, 0.5, 100.0);
			m_SpeedStepsN = m_SpeedStepsN + 1;
		}
		if (KeyState(KeyCode.KC_NEXT) > 0)
		{
			ClearKey(KeyCode.KC_NEXT);
			m_FreeSpeedMps = Math.Clamp(m_FreeSpeedMps * 0.5, 0.5, 100.0);
			m_SpeedStepsN = m_SpeedStepsN + 1;
		}
		if (KeyState(KeyCode.KC_F) > 0)
		{
			ClearKey(KeyCode.KC_F);
			float ab;
			vector qp;
			vector qypr;
			vector qrot[3];
			ReadCamNodeState(m_Cam, ab, qp, qypr, qrot);
			StoreSavedPose("quick_pose", qp, qypr, Camera.GetCurrentFOV());
		}
		float fwd = 0.0;
		if (KeyState(KeyCode.KC_W) > 0)
		{
			fwd = fwd + 1.0;
		}
		if (KeyState(KeyCode.KC_S) > 0)
		{
			fwd = fwd - 1.0;
		}
		float strafe = 0.0;
		if (KeyState(KeyCode.KC_D) > 0)
		{
			strafe = strafe + 1.0;
		}
		if (KeyState(KeyCode.KC_A) > 0)
		{
			strafe = strafe - 1.0;
		}
		float upAxis = 0.0;
		if (KeyState(KeyCode.KC_E) > 0)
		{
			upAxis = upAxis + 1.0;
		}
		if (KeyState(KeyCode.KC_Q) > 0)
		{
			upAxis = upAxis - 1.0;
		}
		float dyaw = 0.0;
		if (KeyState(KeyCode.KC_RIGHT) > 0)
		{
			dyaw = dyaw + 1.0;
		}
		if (KeyState(KeyCode.KC_LEFT) > 0)
		{
			dyaw = dyaw - 1.0;
		}
		float dpitch = 0.0;
		if (KeyState(KeyCode.KC_UP) > 0)
		{
			dpitch = dpitch + 1.0;
		}
		if (KeyState(KeyCode.KC_DOWN) > 0)
		{
			dpitch = dpitch - 1.0;
		}
		if (fwd != 0.0 || strafe != 0.0 || upAxis != 0.0 || dyaw != 0.0 || dpitch != 0.0)
		{
			m_FreeYawDeg = Math.WrapFloat(m_FreeYawDeg + dyaw * m_FreeAngSpeedDegps * timeslice, -180.0, 180.0);
			m_FreePitchDeg = Math.Clamp(m_FreePitchDeg + dpitch * m_FreeAngSpeedDegps * timeslice, -89.0, 89.0);
			vector rot[3];
			vector ypr = Vector(m_FreeYawDeg, m_FreePitchDeg, m_FreeRollDeg);
			Math3D.YawPitchRollMatrix(ypr, rot);
			vector stepVec = (rot[2] * fwd + rot[0] * strafe + Vector(0.0, 1.0, 0.0) * upAxis) * (m_FreeSpeedMps * timeslice);
			m_FreePos = m_FreePos + stepVec;
			vector mat4[4];
			CopyRotToMat4(rot, m_FreePos, mat4);
			m_Cam.SetTransform(mat4);
			m_FreeInputFrames = m_FreeInputFrames + 1;
			m_FreeIntegratedDtS = m_FreeIntegratedDtS + timeslice;
		}
	}

	void TickPathJob(float timeslice)
	{
		if (m_PathHold)
		{
			return;
		}
		if (m_ActiveCamJobId == "" || !m_Jobs)
		{
			return;
		}
		if (m_Jobs.GetState(m_ActiveCamJobId) != "running")
		{
			m_ActiveCamJobId = "";
			return;
		}
		if (m_Jobs.IsDeadmanTripped(m_ActiveCamJobId))
		{
			m_Jobs.EndJob(m_ActiveCamJobId, "failed", "lease_expired");
			return;
		}
		bool firstRow = false;
		if (!m_PathRow0Emitted)
		{
			firstRow = true;
			DSBX_QA_CamKey kEmit0 = m_PathKeys.Get(0);
			EmitPathRow(m_ActiveCamJobId, 0, 0.0, kEmit0.m_FocusDistM);
			m_PathRow0Emitted = true;
			m_PathSeq = 1;
		}
		m_PathDtSumMs = m_PathDtSumMs + timeslice * 1000.0;
		bool reachedEnd = m_PathDtSumMs >= m_PathTargetDurationMs;
		float t = m_PathDurationS;
		if (!reachedEnd)
		{
			t = Math.Min(m_PathDtSumMs / 1000.0, m_PathDurationS);
		}
		int nKeys = m_PathKeys.Count();
		int seg = 0;
		while (seg < nKeys - 2 && t > m_PathKeys.Get(seg + 1).m_TS)
		{
			seg = seg + 1;
		}
		DSBX_QA_CamKey ka = m_PathKeys.Get(seg);
		DSBX_QA_CamKey kb = m_PathKeys.Get(seg + 1);
		float u = 1.0;
		if (!reachedEnd)
		{
			float span = kb.m_TS - ka.m_TS;
			if (span > 0.000001)
			{
				u = Math.Clamp((t - ka.m_TS) / span, 0.0, 1.0);
			}
		}
		float calcFdist = Math.Lerp(ka.m_FocusDistM, kb.m_FocusDistM, u);
		float calcFblur = Math.Lerp(ka.m_FocusBlur, kb.m_FocusBlur, u);

		if (m_PathInterpMode == "scripted")
		{
			vector pos;
			if (m_PathPosMode == "catmull_rom")
			{
				float sParam = Math.Clamp(t / m_PathDurationS, 0.0, 1.0);
				pos = Math3D.Curve(ECurveType.CatmullRom, sParam, m_KeyPoints);
			}
			else
			{
				pos = Vector(Math.Lerp(ka.m_Pos[0], kb.m_Pos[0], u), Math.Lerp(ka.m_Pos[1], kb.m_Pos[1], u), Math.Lerp(ka.m_Pos[2], kb.m_Pos[2], u));
			}
			if (m_PathFault == "cam_path_jump" && !m_JumpInjected && t >= 3.0)
			{
				pos[0] = pos[0] + 2.0;
				m_JumpInjected = true;
			}
			vector rot[3];
			if (m_PathFault == "cam_long_arc")
			{
				vector longYpr = Vector(Math.Lerp(ka.m_Ypr[0], kb.m_Ypr[0], u), Math.Lerp(ka.m_Ypr[1], kb.m_Ypr[1], u), Math.Lerp(ka.m_Ypr[2], kb.m_Ypr[2], u));
				Math3D.YawPitchRollMatrix(longYpr, rot);
			}
			else
			{
				float qa[4];
				qa[0] = ka.m_Q0;
				qa[1] = ka.m_Q1;
				qa[2] = ka.m_Q2;
				qa[3] = ka.m_Q3;
				float qb[4];
				qb[0] = kb.m_Q0;
				qb[1] = kb.m_Q1;
				qb[2] = kb.m_Q2;
				qb[3] = kb.m_Q3;
				float qout[4];
				SlerpQuat(qa, qb, u, qout);
				Math3D.QuatToMatrix(qout, rot);
			}
			vector mat4[4];
			CopyRotToMat4(rot, pos, mat4);
			if (m_Cam && !firstRow)
			{
				m_Cam.SetTransform(mat4);
				float fov = Math.Lerp(ka.m_FovRad, kb.m_FovRad, u);
				if (m_PathFault != "cam_frozen_fov")
				{
					m_Cam.SetFOV(fov);
				}
			}
			if (m_PathFault != "cam_ignore_focus_keys" && !firstRow)
			{
				ApplyCamFocus(calcFdist, calcFblur);
			}
		}
		else
		{
			if (!m_EngineInterpSwitched && nKeys >= 3 && t >= m_PathKeys.Get(1).m_TS && m_CamTarget && m_Cam)
			{
				m_EngineInterpSwitched = true;
				DSBX_QA_CamKey k1 = m_PathKeys.Get(1);
				DSBX_QA_CamKey k2 = m_PathKeys.Get(2);
				m_CamTarget.SetActive(true);
				vector rot2[3];
				Math3D.YawPitchRollMatrix(k2.m_Ypr, rot2);
				vector mat2[4];
				CopyRotToMat4(rot2, k2.m_Pos, mat2);
				m_Cam.SetTransform(mat2);
				m_Cam.SetFOV(k2.m_FovRad);
				m_Cam.SetFocus(k2.m_FocusDistM, k2.m_FocusBlur);
				m_Cam.SetActive(false);
				m_SentFocusDistM = k2.m_FocusDistM;
				m_SentFocusBlur = k2.m_FocusBlur;
				m_SetFocusCallsN = m_SetFocusCallsN + 1;
				Camera.InterpolateTo(m_Cam, k2.m_TS - k1.m_TS, 0);
			}
		}

		if (m_PathFault == "cam_force_quickbar" && m_PathDtSumMs >= 1800.0 && !m_FaultHudForced)
		{
			m_FaultHudForced = true;
			ForceQuickbarAndOverlay();
		}

		if (!firstRow)
		{
			EmitPathRow(m_ActiveCamJobId, m_PathSeq, m_PathDtSumMs, calcFdist);
			m_PathSeq = m_PathSeq + 1;
		}
		if (reachedEnd)
		{
			m_Jobs.EndJob(m_ActiveCamJobId, "done", "");
		}
	}

	void TickSampleJob(float timeslice)
	{
		if (m_ActiveSampleJobId == "" || !m_Jobs)
		{
			return;
		}
		if (m_Jobs.GetState(m_ActiveSampleJobId) != "running")
		{
			m_ActiveSampleJobId = "";
			return;
		}
		if (m_Jobs.IsDeadmanTripped(m_ActiveSampleJobId))
		{
			m_Jobs.EndJob(m_ActiveSampleJobId, "failed", "lease_expired");
			return;
		}
		m_SampleSeq = m_SampleSeq + 1;
		m_SampleDtSumMs = m_SampleDtSumMs + timeslice * 1000.0;
		EmitSampleRow(m_ActiveSampleJobId, m_SampleSeq, m_SampleDtSumMs);
		if (m_SampleDtSumMs >= m_SampleDurationMs)
		{
			m_Jobs.EndJob(m_ActiveSampleJobId, "done", "");
		}
	}

	override void OnTick(float timeslice)
	{
		if (m_SlowStopPending)
		{
			m_SlowStopRemainingMs = m_SlowStopRemainingMs - timeslice * 1000.0;
			if (m_SlowStopRemainingMs <= 0.0)
			{
				m_SlowStopPending = false;
				m_SlowStopRemainingMs = 0.0;
				SetPlayerControlDisabled(false);
			}
		}
		float dt = timeslice;
		if (dt > 0.05)
		{
			dt = 0.05;
		}
		TickFreeCam(dt);
		TickPathJob(dt);
		TickSampleJob(dt);
	}

	override void OnJobEnd(string job_id, string state, string reason)
	{
		if (job_id == m_ActiveCamJobId)
		{
			string pathFault = m_PathFault;
			bool hudByJob = m_HudHiddenByJob;
			m_ActiveCamJobId = "";
			m_PathFault = "";
			m_PathHold = false;
			m_HudHiddenByJob = false;
			if (pathFault == "cam_ignore_focus_keys")
			{
				DestroyCamerasPreserveFocus();
			}
			else
			{
				DestroyCameras();
			}
			if (hudByJob)
			{
				if (pathFault == "cam_restore_showhud")
				{
					DestroyTestOverlay();
					IngameHud hud = GetIngameHud();
					if (hud)
					{
						hud.ShowHud(true);
					}
					m_HudHidden = false;
				}
				else
				{
					RestoreHudSavedState();
				}
			}
			if (pathFault == "cam_slow_stop")
			{
				m_SlowStopPending = true;
				m_SlowStopRemainingMs = 1500.0;
			}
			else
			{
				m_SlowStopPending = false;
				m_SlowStopRemainingMs = 0.0;
				SetPlayerControlDisabled(false);
			}
		}
		if (job_id == m_ActiveSampleJobId)
		{
			m_ActiveSampleJobId = "";
		}
	}

	override void OnRpc(PlayerIdentity sender, Object target, int rpc_type, ParamsReadContext ctx)
	{
	}

	override void OnShutdown()
	{
		m_FreeCamActive = false;
		m_SlowStopPending = false;
		m_SlowStopRemainingMs = 0.0;
		m_ActiveCamJobId = "";
		m_ActiveSampleJobId = "";
		m_PathFault = "";
		m_HudHiddenByJob = false;
		DestroyCameras();
		DestroyTestOverlay();
		RestoreHudSavedState();
		SetPlayerControlDisabled(false);
		CleanupFixtureEntities();
	}
}
