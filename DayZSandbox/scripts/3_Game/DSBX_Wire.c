class DSBX_Wire
{
	static bool IsIdCode(int c)
	{
		if (c >= 48 && c <= 57)
		{
			return true;
		}
		if (c >= 65 && c <= 90)
		{
			return true;
		}
		if (c >= 97 && c <= 122)
		{
			return true;
		}
		if (c == 95 || c == 46 || c == 58 || c == 45)
		{
			return true;
		}
		return false;
	}

	static bool ValidId(string s)
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
			if (!IsIdCode(c))
			{
				return false;
			}
			i = i + 1;
		}
		return true;
	}

	static string WireId(string s)
	{
		if (!ValidId(s))
		{
			return "";
		}
		return "\"" + s + "\"";
	}

	static string HexDigit(int v)
	{
		string digits = "0123456789abcdef";
		return digits.Substring(v & 15, 1);
	}

	static string Hex8(int val)
	{
		string outHex = "";
		int shift = 28;
		while (shift >= 0)
		{
			int nibble = (val >> shift) & 15;
			outHex = outHex + HexDigit(nibble);
			shift = shift - 4;
		}
		return outHex;
	}

	static string WireText(string s)
	{
		string outStr = "\"";
		int n = s.Length();
		int i = 0;
		while (i < n)
		{
			string ch = s.Substring(i, 1);
			int c = ch.ToAscii();
			if (c == 34)
			{
				outStr = outStr + "\\\"";
			}
			else if (c == 92)
			{
				outStr = outStr + "\\\\";
			}
			else if (c >= 0 && c < 32)
			{
				int hi = (c >> 4) & 15;
				int lo = c & 15;
				string hiHex = HexDigit(hi);
				string loHex = HexDigit(lo);
				outStr = outStr + "\\u00" + hiHex + loHex;
			}
			else
			{
				outStr = outStr + ch;
			}
			i = i + 1;
		}
		outStr = outStr + "\"";
		return outStr;
	}

	static string MakeUuid32()
	{
		int uuid[4];
		UUIDApi.Generate(uuid);
		string raw = UUIDApi.FormatString(uuid);
		string partA = raw.Substring(0, 8);
		string partB = raw.Substring(9, 4);
		string partC = raw.Substring(14, 4);
		string partD = raw.Substring(19, 4);
		string partE = raw.Substring(24, 12);
		string outId = partA + partB + partC + partD + partE;
		outId.ToLower();
		return outId;
	}

	static string ModsetHash(array<string> sortedModset)
	{
		string joined = "";
		if (sortedModset)
		{
			int i = 0;
			while (i < sortedModset.Count())
			{
				if (i > 0)
				{
					joined = joined + "\n";
				}
				joined = joined + sortedModset.Get(i);
				i = i + 1;
			}
		}
		string outHash = "";
		int s = 0;
		while (s < 8)
		{
			string salted = s.ToString() + "|" + joined;
			int h = salted.Hash();
			outHash = outHash + Hex8(h);
			s = s + 1;
		}
		return outHash;
	}

	static string HelloBody(string role, string inst, string epoch, string modVer, string build, string mapName, int worldSize, array<string> modset)
	{
		string roleJson = WireId(role);
		string instJson = WireId(inst);
		string epochJson = WireId(epoch);
		if (roleJson == "" || instJson == "" || epochJson == "")
		{
			return "";
		}
		string modVerJson = WireText(modVer);
		string buildJson = WireText(build);
		string body = "{\"proto\":\"dsbx1\",\"peer\":" + roleJson + ",\"inst\":" + instJson + ",\"epoch\":" + epochJson + ",\"mod_ver\":" + modVerJson + ",\"build\":" + buildJson;
		if (role == "server")
		{
			string modsetItems = "";
			if (modset)
			{
				int i = 0;
				while (i < modset.Count())
				{
					if (i > 0)
					{
						modsetItems = modsetItems + ",";
					}
					modsetItems = modsetItems + WireText(modset.Get(i));
					i = i + 1;
				}
			}
			body = body + ",\"map\":" + WireText(mapName);
			body = body + ",\"world_size\":" + worldSize;
			body = body + ",\"modset\":[" + modsetItems + "]";
			body = body + ",\"actor_engine\":" + WireText(DSBX_ActorEngineRegistry.EngineName());
			body = body + ",\"scene\":1";
		}
		body = body + "}";
		return body;
	}

	static string WorldReadJson(DSBX_World world, DSBX_Scene scene = null, DSBX_Args args = null)
	{
		if (!world)
		{
			return "{}";
		}
		if (args && args.f2 == 1 && scene && args.doc_id != "")
		{
			return DSBX_SceneWire.SceneReadJson(world.GetEpoch(), scene, args.doc_id, "");
		}
		string epochJson = WireId(world.GetEpoch());
		string regShaJson = WireId(world.GetRegistrySha256());
		if (epochJson == "" || regShaJson == "")
		{
			return "{}";
		}
		string genJson = "null";
		DSBX_Generation gen = world.GetGeneration();
		if (gen)
		{
			string sessJson = WireId(gen.session);
			string opJson = WireId(gen.op_id);
			string hashJson = WireId(gen.hash);
			if (sessJson == "" || opJson == "" || hashJson == "")
			{
				return "{}";
			}
			genJson = "{\"session\":" + sessJson + ",\"op_id\":" + opJson + ",\"rev\":" + gen.rev + ",\"hash\":" + hashJson + "}";
		}
		string body = "{\"epoch\":" + epochJson + ",\"generation\":" + genJson + ",\"registry_n\":" + world.GetRegistryN() + ",\"registry_sha256\":" + regShaJson + "}";
		return body;
	}

	static string ResultBody(string opId, string session, string epoch, string status, string reason, bool dup, string readJson)
	{
		string opJson = WireId(opId);
		string sessJson = WireId(session);
		string epochJson = WireId(epoch);
		string statusJson = WireId(status);
		if (opJson == "" || sessJson == "" || epochJson == "" || statusJson == "")
		{
			return "";
		}
		string reasonJson = "null";
		if (reason != "")
		{
			reasonJson = WireId(reason);
			if (reasonJson == "")
			{
				return "";
			}
		}
		string dupJson = "false";
		if (dup)
		{
			dupJson = "true";
		}
		string rJson = readJson;
		if (rJson == "")
		{
			rJson = "{}";
		}
		return "{\"op_id\":" + opJson + ",\"session\":" + sessJson + ",\"epoch\":" + epochJson + ",\"status\":" + statusJson + ",\"reason\":" + reasonJson + ",\"dup\":" + dupJson + ",\"read\":" + rJson + "}";
	}

	static string ResultTooLargeBody(string opId, string session, string epoch, bool dup)
	{
		return ResultBody(opId, session, epoch, "error", "result_too_large", dup, "{}");
	}

	static string CatalogPageBody(string catalogId, int page, int pages, string build, string modsetHash, array<string> classNames, array<string> baseNames)
	{
		string catJson = WireId(catalogId);
		string hashJson = WireId(modsetHash);
		if (catJson == "" || hashJson == "")
		{
			return "";
		}
		string buildJson = WireText(build);
		string items = "";
		if (classNames && baseNames)
		{
			int i = 0;
			int n = classNames.Count();
			while (i < n)
			{
				string clsJson = WireId(classNames.Get(i));
				string baseJson = WireId(baseNames.Get(i));
				if (clsJson == "" || baseJson == "")
				{
					return "";
				}
				if (i > 0)
				{
					items = items + ",";
				}
				items = items + "[" + clsJson + "," + baseJson + "]";
				i = i + 1;
			}
		}
		return "{\"catalog_id\":" + catJson + ",\"page\":" + page + ",\"pages\":" + pages + ",\"build\":" + buildJson + ",\"modset_hash\":" + hashJson + ",\"classes\":[" + items + "]}";
	}
}
