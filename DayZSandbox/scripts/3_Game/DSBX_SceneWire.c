class DSBX_SceneWire
{
	static bool IsAsciiNonEmpty(string s)
	{
		int n = s.Length();
		if (n <= 0)
		{
			return false;
		}
		int i = 0;
		while (i < n)
		{
			int c = s.Substring(i, 1).ToAscii();
			if (c <= 0 || c >= 128)
			{
				return false;
			}
			i = i + 1;
		}
		return true;
	}

	static bool IsLowerHexChar(int c)
	{
		if (c >= 48 && c <= 57)
		{
			return true;
		}
		if (c >= 97 && c <= 102)
		{
			return true;
		}
		return false;
	}

	static bool ValidDocId(string s)
	{
		if (s.Length() != 10)
		{
			return false;
		}
		if (s.Substring(0, 2) != "d-")
		{
			return false;
		}
		int i = 2;
		while (i < 10)
		{
			int c = s.Substring(i, 1).ToAscii();
			if (!IsLowerHexChar(c))
			{
				return false;
			}
			i = i + 1;
		}
		return true;
	}

	// 0 = objeto, 1 = infectado, 2 = animal, -1 = invalido
	static int LidKind(string lid)
	{
		if (lid.Length() < 4)
		{
			return -1;
		}
		string pref = lid.Substring(0, 4);
		if (pref == "obj-")
		{
			return 0;
		}
		if (pref == "zmb-")
		{
			return 1;
		}
		if (pref == "ani-")
		{
			return 2;
		}
		return -1;
	}

	// Patron ^(obj|zmb|ani)-(0[1-9]|[1-9][0-9]+)$ con digitos ASCII y <= 10 caracteres (F2b §3.6).
	static bool ValidLid(string lid)
	{
		int n = lid.Length();
		if (n < 6 || n > 10)
		{
			return false;
		}
		if (LidKind(lid) < 0)
		{
			return false;
		}
		int first = lid.Substring(4, 1).ToAscii();
		if (first < 48 || first > 57)
		{
			return false;
		}
		if (first == 48)
		{
			if (n != 6)
			{
				return false;
			}
			int second = lid.Substring(5, 1).ToAscii();
			if (second < 49 || second > 57)
			{
				return false;
			}
			return true;
		}
		int i = 5;
		while (i < n)
		{
			int c = lid.Substring(i, 1).ToAscii();
			if (c < 48 || c > 57)
			{
				return false;
			}
			i = i + 1;
		}
		return true;
	}

	// NaN e infinito fallan esta comparacion sin depender de ninguna API adicional.
	static bool IsFiniteCoord(float v, float absMax)
	{
		if (v >= -absMax && v <= absMax)
		{
			return true;
		}
		return false;
	}

	static int WorldLimitMm(int worldSize)
	{
		if (worldSize <= 0)
		{
			return 0;
		}
		if (worldSize >= DSBX_SceneConst.MAX_WORLD_SIZE)
		{
			return DSBX_SceneConst.MAX_XZ_MM;
		}
		return worldSize * 1000;
	}

	static bool MetersToMmChecked(float v, int minMm, int maxMm, out int outMm)
	{
		outMm = 0;
		if (!IsFiniteCoord(v, 100000.0))
		{
			return false;
		}
		int mm = (int)Math.Round(v * 1000.0);
		if (mm < minMm || mm > maxMm)
		{
			return false;
		}
		outMm = mm;
		return true;
	}

	// §3.1: yaw_mdeg en [0, 360000), normalizado despues de redondear (359.9996 -> 0).
	static bool YawDegToMdegChecked(float yawDeg, out int outMdeg)
	{
		outMdeg = 0;
		if (!IsFiniteCoord(yawDeg, 360000.0))
		{
			return false;
		}
		int turns = (int)(yawDeg / 360.0);
		float norm = yawDeg - (turns * 360.0);
		while (norm < 0.0)
		{
			norm = norm + 360.0;
		}
		while (norm >= 360.0)
		{
			norm = norm - 360.0;
		}
		int mdeg = (int)Math.Round(norm * 1000.0);
		mdeg = mdeg % DSBX_SceneConst.YAW_MDEG_MOD;
		if (mdeg < 0)
		{
			mdeg = mdeg + DSBX_SceneConst.YAW_MDEG_MOD;
		}
		outMdeg = mdeg;
		return true;
	}

	static int RatioToMilli(float ratio)
	{
		if (!(ratio >= 0.0))
		{
			return 0;
		}
		if (ratio >= 1.0)
		{
			return DSBX_SceneConst.MAX_HP_MILLI;
		}
		int m = (int)Math.Round(ratio * 1000.0);
		if (m < 0)
		{
			return 0;
		}
		if (m > DSBX_SceneConst.MAX_HP_MILLI)
		{
			return DSBX_SceneConst.MAX_HP_MILLI;
		}
		return m;
	}

	static string SceneGenJson(DSBX_SceneGen gen)
	{
		if (!gen)
		{
			return "null";
		}
		string sessJson = DSBX_Wire.WireId(gen.m_Session);
		string opJson = DSBX_Wire.WireId(gen.m_OpId);
		string hashJson = DSBX_Wire.WireId(gen.m_Hash);
		string planJson = DSBX_Wire.WireId(gen.m_PlanSha256);
		if (sessJson == "" || opJson == "" || hashJson == "" || planJson == "")
		{
			return "";
		}
		return "{\"session\":" + sessJson + ",\"op_id\":" + opJson + ",\"rev\":" + gen.m_Rev.ToString() + ",\"hash\":" + hashJson + ",\"plan_sha256\":" + planJson + "}";
	}

	static string SceneBlockJson(string epoch, DSBX_Scene scene, string docId)
	{
		string docJson = DSBX_Wire.WireId(docId);
		if (docJson == "")
		{
			return "";
		}
		int genN = 0;
		int sceneN = 0;
		int retainedN = 0;
		string retainedItems = "";
		string pendingJson = "null";
		string lastJson = "null";

		if (scene)
		{
			sceneN = scene.CountSceneRecords(epoch, docId);
			DSBX_SceneState st = scene.GetSceneState(docId, false);
			if (st)
			{
				genN = st.m_GenN;
				retainedN = st.m_RetainedN;
				int i = 0;
				while (i < st.m_Retained.Count() && i < DSBX_SceneConst.MAX_RETAINED_LIST)
				{
					string rLidJson = DSBX_Wire.WireId(st.m_Retained.Get(i));
					if (rLidJson == "")
					{
						return "";
					}
					if (i > 0)
					{
						retainedItems = retainedItems + ",";
					}
					retainedItems = retainedItems + rLidJson;
					i = i + 1;
				}
				string pSess = "";
				string pOp = "";
				int pN = 0;
				if (scene.GetPendingReport(epoch, docId, pSess, pOp, pN))
				{
					string pSessJson = DSBX_Wire.WireId(pSess);
					string pOpJson = DSBX_Wire.WireId(pOp);
					if (pSessJson == "" || pOpJson == "")
					{
						return "";
					}
					pendingJson = "{\"session\":" + pSessJson + ",\"op_id\":" + pOpJson + ",\"n\":" + pN.ToString() + "}";
				}
				if (st.m_Last)
				{
					string lSessJson = DSBX_Wire.WireId(st.m_Last.m_Session);
					string lOpJson = DSBX_Wire.WireId(st.m_Last.m_OpId);
					string lVerbJson = DSBX_Wire.WireId(st.m_Last.m_Verb);
					string lOutJson = DSBX_Wire.WireId(st.m_Last.m_Outcome);
					if (lSessJson == "" || lOpJson == "" || lVerbJson == "" || lOutJson == "")
					{
						return "";
					}
					lastJson = "{\"session\":" + lSessJson + ",\"op_id\":" + lOpJson + ",\"verb\":" + lVerbJson + ",\"outcome\":" + lOutJson + "}";
				}
			}
		}

		return "{\"doc_id\":" + docJson + ",\"gen_n\":" + genN.ToString() + ",\"n\":" + sceneN.ToString() + ",\"retained_n\":" + retainedN.ToString() + ",\"retained\":[" + retainedItems + "],\"pending\":" + pendingJson + ",\"last\":" + lastJson + "}";
	}

	static string CheckpointRowJson(DSBX_CheckpointRow row)
	{
		if (!row)
		{
			return "";
		}
		string lidJson = DSBX_Wire.WireId(row.m_Lid);
		if (lidJson == "")
		{
			return "";
		}
		string gyJson = "null";
		if (row.m_HasGy)
		{
			gyJson = row.m_GyMm.ToString();
		}
		if (!row.m_HasPose)
		{
			return "[" + lidJson + ",-1,null,null,null,null," + gyJson + "]";
		}
		return "[" + lidJson + "," + row.m_Ci.ToString() + "," + row.m_XMm.ToString() + "," + row.m_YMm.ToString() + "," + row.m_ZMm.ToString() + "," + row.m_YawMdeg.ToString() + "," + gyJson + "]";
	}

	static string ObsCheckpointJson(array<ref DSBX_CheckpointRow> rows)
	{
		string items = "";
		if (rows)
		{
			int i = 0;
			while (i < rows.Count())
			{
				string rowJson = CheckpointRowJson(rows.Get(i));
				if (rowJson == "")
				{
					return "";
				}
				if (i > 0)
				{
					items = items + ",";
				}
				items = items + rowJson;
				i = i + 1;
			}
		}
		return "{\"at\":\"checkpoint\",\"rows\":[" + items + "]}";
	}

	static string NowRowAliveJson(string lid, int xMm, int yMm, int zMm, int yawMdeg, int hpMilli, int nOwn, int nForeign)
	{
		string lidJson = DSBX_Wire.WireId(lid);
		if (lidJson == "")
		{
			return "";
		}
		return "[" + lidJson + "," + xMm.ToString() + "," + yMm.ToString() + "," + zMm.ToString() + "," + yawMdeg.ToString() + "," + hpMilli.ToString() + "," + nOwn.ToString() + "," + nForeign.ToString() + "]";
	}

	// M15: raiz muerta -> cinco nulos y contadores a 0.
	static string NowRowDeadJson(string lid)
	{
		string lidJson = DSBX_Wire.WireId(lid);
		if (lidJson == "")
		{
			return "";
		}
		return "[" + lidJson + ",null,null,null,null,null,0,0]";
	}

	static string ObsNowJson(array<string> rowJsons)
	{
		string items = "";
		if (rowJsons)
		{
			int i = 0;
			while (i < rowJsons.Count())
			{
				if (i > 0)
				{
					items = items + ",";
				}
				items = items + rowJsons.Get(i);
				i = i + 1;
			}
		}
		return "{\"at\":\"now\",\"rows\":[" + items + "]}";
	}

	static string SceneReadJson(string epoch, DSBX_Scene scene, string docId, string obsJson)
	{
		string epochJson = DSBX_Wire.WireId(epoch);
		if (epochJson == "" || !scene)
		{
			return "{}";
		}
		int regN = scene.GetRegistryCount(epoch);
		string regSha = scene.ComputeRegistryHash(epoch);
		string regShaJson = DSBX_Wire.WireId(regSha);
		if (regShaJson == "")
		{
			return "{}";
		}
		DSBX_SceneState st = scene.GetSceneState(docId, false);
		DSBX_SceneGen gen = null;
		if (st)
		{
			gen = st.m_Generation;
		}
		string genJson = SceneGenJson(gen);
		if (genJson == "")
		{
			return "{}";
		}
		string sceneJson = SceneBlockJson(epoch, scene, docId);
		if (sceneJson == "")
		{
			return "{}";
		}
		string body = "{\"epoch\":" + epochJson + ",\"generation\":" + genJson + ",\"registry_n\":" + regN.ToString() + ",\"registry_sha256\":" + regShaJson + ",\"scene\":" + sceneJson;
		if (obsJson != "")
		{
			body = body + ",\"obs\":" + obsJson;
		}
		body = body + "}";
		return body;
	}
}
