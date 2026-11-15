// S-mapa: lecturas del mundo, localizacion de rasgos y colocacion en suelo (prefijo map_, 0 constantes RPC).
// Tres verbos instantaneos que terminan en OnStartOp. El estado de transporte (bad_args / world_unavailable) va en
// res.status / res.reason; el funcional (decision_id / reject_reason_id) va dentro del payload.
class DSBX_QA_X_Map : DSBX_QA_Ext
{
	protected int m_SpawnSeqN;

	void DSBX_QA_X_Map()
	{
		m_SpawnSeqN = 0;
	}

	override void Init(DSBX_QA_Probe probe)
	{
		super.Init(probe);
	}

	override bool Handles(string verb, string role)
	{
		if (role == "server" && (verb == "map_world_read" || verb == "map_feature_locate" || verb == "map_place_ground"))
		{
			return true;
		}
		return false;
	}

	override void OnTick(float timeslice)
	{
	}

	override void OnJobEnd(string job_id, string state, string reason)
	{
	}

	override void OnRpc(PlayerIdentity sender, Object target, int rpc_type, ParamsReadContext ctx)
	{
	}

	override void OnShutdown()
	{
	}

	// ---- utilidades de argumentos y de respuesta -------------------------------------------------------------

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

	void AddS(DSBX_QA_Result res, string key, string value)
	{
		res.read.sk.Insert(key);
		res.read.sv.Insert(value);
	}

	void AddN(DSBX_QA_Result res, string key, float value)
	{
		res.read.nk.Insert(key);
		res.read.nv.Insert(value);
	}

	string Clip(string value)
	{
		if (value.Length() > 32)
		{
			return value.Substring(0, 32);
		}
		return value;
	}

	float BoolF(bool value)
	{
		if (value)
		{
			return 1.0;
		}
		return 0.0;
	}

	float SeaB(float x, float z, float y)
	{
		float seaLevel = g_Game.SurfaceGetSeaLevel();
		if (g_Game.SurfaceIsSea(x, z) || y <= seaLevel)
		{
			return 1.0;
		}
		return 0.0;
	}

	bool OutOfMap(float x, float z, float worldSize)
	{
		return x < 0.0 || x > worldSize || z < 0.0 || z > worldSize;
	}

	override void OnStartOp(DSBX_QA_Op op, DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string verb = op.verb;
		string fault = m_Probe.GetOpFault();
		if (fault != "" && fault != "ignore_elevated_surface" && fault != "spawn_then_reject")
		{
			Reject(res, "bad_args");
			return;
		}
		if (fault != "" && verb != "map_place_ground")
		{
			Reject(res, "bad_args");
			return;
		}
		if (args.rows != 0 || args.ncol.Count() != 0 || args.scol.Count() != 0)
		{
			Reject(res, "bad_args");
			return;
		}
		if (verb == "map_world_read")
		{
			DoWorldRead(args, res);
			return;
		}
		if (verb == "map_feature_locate")
		{
			DoFeatureLocate(args, res);
			return;
		}
		if (verb == "map_place_ground")
		{
			DoPlaceGround(args, res, fault);
			return;
		}
		Reject(res, "unknown_verb");
	}

	// ---- map_world_read ---------------------------------------------------------------------------------------

	void DoWorldRead(DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string mode;
		float x0;
		float z0;
		float step;
		float rowF;
		float chunkF;
		if (!GetStr(args, "mode_id", mode) || (mode != "grid_row" && mode != "patch_row"))
		{
			Reject(res, "bad_args");
			return;
		}
		if (!GetNum(args, "x0_m", x0) || !GetNum(args, "z0_m", z0) || !GetNum(args, "step_m", step) || !GetNum(args, "row_n", rowF) || !GetNum(args, "chunk_n", chunkF))
		{
			Reject(res, "bad_args");
			return;
		}
		if (!m_Probe.IsFiniteF(x0) || !m_Probe.IsFiniteF(z0) || !m_Probe.IsFiniteF(step) || !m_Probe.IsIntF(rowF) || !m_Probe.IsIntF(chunkF))
		{
			Reject(res, "bad_args");
			return;
		}
		int chunkN = (int)chunkF;
		if (chunkN < 1 || chunkN > 8 || step <= 0.0 || rowF < 0.0)
		{
			Reject(res, "bad_args");
			return;
		}
		World world = g_Game.GetWorld();
		if (!world)
		{
			res.status = "error";
			res.reason = "world_unavailable";
			return;
		}
		res.status = "done";
		res.reason = "";
		res.read.has.Insert("payload");
		AddS(res, "world_name", g_Game.GetWorldName());
		AddS(res, "mode_id", mode);
		AddN(res, "world_size_m", world.GetWorldSize());
		AddN(res, "sea_level_m", g_Game.SurfaceGetSeaLevel());
		AddN(res, "x0_m", x0);
		AddN(res, "z0_m", z0);
		AddN(res, "step_m", step);
		AddN(res, "row_n", rowF);
		AddN(res, "tick_ms", m_Probe.NowMs());
		AddN(res, "frame", m_Probe.m_Frame);
		res.read.ncol.Insert("y_m");
		res.read.ncol.Insert("sea_b");
		int c = 0;
		while (c < chunkN)
		{
			float x = x0 + (float)c * step;
			float y = g_Game.SurfaceY(x, z0);
			res.read.ncell.Insert(y);
			res.read.ncell.Insert(SeaB(x, z0, y));
			c = c + 1;
		}
		res.read.rows = chunkN;
	}

	// ---- map_feature_locate -----------------------------------------------------------------------------------

	// Malla 16x16 (fila r de arriba abajo desde z_max, columna c desde x_min): x, z, y y sea_b por celda.
	void ReadGrid(float xMin, float zMax, array<float> gx, array<float> gz, array<float> gy, array<float> gs)
	{
		int r = 0;
		while (r < 16)
		{
			int c = 0;
			while (c < 16)
			{
				float x = xMin + 3.75 * (float)c;
				float z = zMax - 3.75 * (float)r;
				float y = g_Game.SurfaceY(x, z);
				gx.Insert(x);
				gz.Insert(z);
				gy.Insert(y);
				gs.Insert(SeaB(x, z, y));
				c = c + 1;
			}
			r = r + 1;
		}
	}

	bool IsBorder(int r, int c)
	{
		return r == 0 || r == 15 || c == 0 || c == 15;
	}

	// Cima: false si no hay rasgo. Salida: centroide de M_srv, y_max, prominencia y las 2 celdas de auditoria.
	bool FindPeak(array<float> gx, array<float> gz, array<float> gy, array<float> gs, out float srvX, out float srvZ, out float srvY, out float prom, out int auditA, out int auditB)
	{
		srvX = 0.0;
		srvZ = 0.0;
		srvY = 0.0;
		prom = 0.0;
		auditA = 0;
		auditB = 0;
		float yMax = gy.Get(0);
		float yBorder = -1000000.0;
		int i = 0;
		while (i < 256)
		{
			if (gs.Get(i) != 0.0)
			{
				return false;
			}
			if (gy.Get(i) > yMax)
			{
				yMax = gy.Get(i);
			}
			i = i + 1;
		}
		int r = 0;
		while (r < 16)
		{
			int c = 0;
			while (c < 16)
			{
				if (IsBorder(r, c) && gy.Get(r * 16 + c) > yBorder)
				{
					yBorder = gy.Get(r * 16 + c);
				}
				c = c + 1;
			}
			r = r + 1;
		}
		prom = yMax - yBorder;
		if (prom < 5.0)
		{
			return false;
		}
		int n = 0;
		float sx = 0.0;
		float sz = 0.0;
		auditA = -1;
		auditB = -1;
		r = 0;
		while (r < 16)
		{
			int cc = 0;
			while (cc < 16)
			{
				int idx = r * 16 + cc;
				if (IsBorder(r, cc))
				{
					if (auditA < 0 && gy.Get(idx) == yBorder)
					{
						auditA = idx;
					}
				}
				else
				{
					if (gy.Get(idx) >= yMax - 0.5)
					{
						n = n + 1;
						sx = sx + gx.Get(idx);
						sz = sz + gz.Get(idx);
					}
					if (auditB < 0 && gy.Get(idx) == yMax)
					{
						auditB = idx;
					}
				}
				cc = cc + 1;
			}
			r = r + 1;
		}
		if (n < 1 || n > 9 || auditA < 0 || auditB < 0)
		{
			return false;
		}
		srvX = sx / (float)n;
		srvZ = sz / (float)n;
		srvY = yMax;
		return true;
	}

	// Costa: transecto central de 16 muestras con un unico k* en 3..13 (tierra antes, mar despues).
	bool FindCoast(bool ns, array<float> gx, array<float> gz, array<float> gy, array<float> gs, out float srvX, out float srvZ, out float srvY, out float prom, out int auditA, out int auditB)
	{
		srvX = 0.0;
		srvZ = 0.0;
		srvY = 0.0;
		prom = 0.0;
		auditA = 0;
		auditB = 0;
		int found = 0;
		int kStar = 0;
		int k = 3;
		while (k <= 13)
		{
			bool ok = true;
			int i = 0;
			while (i < 16)
			{
				int idx = 8 * 16 + i;
				if (ns)
				{
					idx = i * 16 + 8;
				}
				float want = 0.0;
				if (i >= k)
				{
					want = 1.0;
				}
				if (gs.Get(idx) != want)
				{
					ok = false;
				}
				i = i + 1;
			}
			if (ok)
			{
				found = found + 1;
				kStar = k;
			}
			k = k + 1;
		}
		if (found != 1)
		{
			return false;
		}
		int landIdx = 8 * 16 + (kStar - 1);
		int seaIdx = 8 * 16 + kStar;
		if (ns)
		{
			landIdx = (kStar - 1) * 16 + 8;
			seaIdx = kStar * 16 + 8;
		}
		float yLand = gy.Get(landIdx);
		prom = yLand - g_Game.SurfaceGetSeaLevel();
		if (prom < 0.20)
		{
			return false;
		}
		if (ns)
		{
			srvX = gx.Get(8);
			srvZ = gz.Get(0) - ((float)kStar - 0.5) * 3.75;
		}
		else
		{
			srvX = gx.Get(0) + ((float)kStar - 0.5) * 3.75;
			srvZ = gz.Get(8 * 16);
		}
		srvY = yLand;
		auditA = landIdx;
		auditB = seaIdx;
		return true;
	}

	void DoFeatureLocate(DSBX_QA_Args args, DSBX_QA_Result res)
	{
		string pointId;
		string kind;
		string mode;
		float xMin;
		float zMin;
		float xMax;
		float zMax;
		float reqX = 0.0;
		float reqZ = 0.0;
		if (!GetStr(args, "point_id", pointId) || pointId == "" || !GetStr(args, "feature_kind", kind) || !GetStr(args, "mode_id", mode))
		{
			Reject(res, "bad_args");
			return;
		}
		if ((kind != "relief_peak" && kind != "coast_ns" && kind != "coast_ew") || (mode != "calibrate" && mode != "verify"))
		{
			Reject(res, "bad_args");
			return;
		}
		if (!GetNum(args, "x_min_m", xMin) || !GetNum(args, "z_min_m", zMin) || !GetNum(args, "x_max_m", xMax) || !GetNum(args, "z_max_m", zMax))
		{
			Reject(res, "bad_args");
			return;
		}
		if (!m_Probe.IsFiniteF(xMin) || !m_Probe.IsFiniteF(zMin) || !m_Probe.IsFiniteF(xMax) || !m_Probe.IsFiniteF(zMax) || xMax <= xMin || zMax <= zMin)
		{
			Reject(res, "bad_args");
			return;
		}
		bool hasReqX = GetNum(args, "req_x_m", reqX);
		bool hasReqZ = GetNum(args, "req_z_m", reqZ);
		if (mode == "calibrate")
		{
			if (hasReqX || hasReqZ)
			{
				Reject(res, "bad_args");
				return;
			}
			reqX = 0.0;
			reqZ = 0.0;
		}
		else
		{
			if (!hasReqX || !hasReqZ || !m_Probe.IsFiniteF(reqX) || !m_Probe.IsFiniteF(reqZ))
			{
				Reject(res, "bad_args");
				return;
			}
		}
		World world = g_Game.GetWorld();
		if (!world)
		{
			res.status = "error";
			res.reason = "world_unavailable";
			return;
		}
		float worldSize = world.GetWorldSize();
		string decision = "located";
		string reasonId = "";
		bool found = false;
		float srvX = 0.0;
		float srvZ = 0.0;
		float srvY = 0.0;
		float prom = 0.0;
		float errXz = 0.0;
		float errRefl = 0.0;
		float a0x = 0.0;
		float a0z = 0.0;
		float a0y = 0.0;
		float a0s = 0.0;
		float a1x = 0.0;
		float a1z = 0.0;
		float a1y = 0.0;
		float a1s = 0.0;
		if (mode == "verify" && OutOfMap(reqX, reqZ, worldSize))
		{
			decision = "rejected";
			reasonId = "out_of_map";
		}
		else
		{
			ref array<float> gx = new array<float>();
			ref array<float> gz = new array<float>();
			ref array<float> gy = new array<float>();
			ref array<float> gs = new array<float>();
			ReadGrid(xMin, zMax, gx, gz, gy, gs);
			int auditA = 0;
			int auditB = 0;
			if (kind == "relief_peak")
			{
				found = FindPeak(gx, gz, gy, gs, srvX, srvZ, srvY, prom, auditA, auditB);
			}
			else
			{
				found = FindCoast(kind == "coast_ns", gx, gz, gy, gs, srvX, srvZ, srvY, prom, auditA, auditB);
			}
			if (found)
			{
				a0x = gx.Get(auditA);
				a0z = gz.Get(auditA);
				a0y = gy.Get(auditA);
				a0s = gs.Get(auditA);
				a1x = gx.Get(auditB);
				a1z = gz.Get(auditB);
				a1y = gy.Get(auditB);
				a1s = gs.Get(auditB);
			}
			if (!found)
			{
				decision = "rejected";
				reasonId = "feature_not_found";
			}
			else if (mode == "verify")
			{
				float dx = reqX - srvX;
				float dz = reqZ - srvZ;
				errXz = Math.Sqrt(dx * dx + dz * dz);
				errRefl = m_Probe.AbsF((worldSize - reqZ) - srvZ);
				if (errXz >= 10.0 && errRefl < 50.0 && m_Probe.AbsF(dx) < 50.0)
				{
					decision = "rejected";
					reasonId = "inverted_axis";
				}
				else if (errXz >= 10.0)
				{
					decision = "rejected";
					reasonId = "verification_error_exceeded";
				}
				else
				{
					decision = "verified";
					reasonId = "";
				}
			}
		}
		res.status = "done";
		res.reason = "";
		res.read.has.Insert("payload");
		AddS(res, "point_id", Clip(pointId));
		AddS(res, "mode_id", mode);
		AddS(res, "decision_id", decision);
		AddS(res, "reject_reason_id", reasonId);
		AddN(res, "req_x_m", reqX);
		AddN(res, "req_z_m", reqZ);
		AddN(res, "srv_feature_found_b", BoolF(found));
		AddN(res, "srv_x_m", srvX);
		AddN(res, "srv_y_m", srvY);
		AddN(res, "srv_z_m", srvZ);
		AddN(res, "prominence_m", prom);
		AddN(res, "err_xz_m", errXz);
		AddN(res, "err_reflected_z_m", errRefl);
		AddN(res, "tick_ms", m_Probe.NowMs());
		AddN(res, "frame", m_Probe.m_Frame);
		res.read.ncol.Insert("sx_m");
		res.read.ncol.Insert("sz_m");
		res.read.ncol.Insert("y_m");
		res.read.ncol.Insert("sea_b");
		res.read.ncell.Insert(a0x);
		res.read.ncell.Insert(a0z);
		res.read.ncell.Insert(a0y);
		res.read.ncell.Insert(a0s);
		res.read.ncell.Insert(a1x);
		res.read.ncell.Insert(a1z);
		res.read.ncell.Insert(a1y);
		res.read.ncell.Insert(a1s);
		res.read.rows = 2;
	}

	// ---- map_place_ground -------------------------------------------------------------------------------------

	// UNICA llamada a CreateObjectEx. Cuenta la creacion antes de cualquier otra comprobacion y lee del objeto
	// creado su identidad, clase, posicion y caja local. No borra: lo hace quien llama con ObjectDelete.
	Object SpawnTrackedObject(string class_name, vector pos, int flags, out int ent_id, out string obs_class, out vector obs_pos, out float bbox_min_y, out float bbox_max_y)
	{
		ent_id = 0;
		obs_class = "";
		obs_pos = "0 0 0";
		bbox_min_y = 0.0;
		bbox_max_y = 0.0;
		Object obj = g_Game.CreateObjectEx(class_name, pos, flags);
		if (!obj)
		{
			return null;
		}
		m_SpawnSeqN = m_SpawnSeqN + 1;
		ent_id = obj.GetID();
		g_Game.ObjectGetType(obj, obs_class);
		obs_pos = obj.GetPosition();
		vector box[2];
		obj.ClippingInfo(box);
		bbox_min_y = box[0][1];
		bbox_max_y = box[1][1];
		return obj;
	}

	int CountAt(float x, float y, float z)
	{
		ref array<Object> objs = new array<Object>();
		ref array<CargoBase> cargos = new array<CargoBase>();
		g_Game.GetObjectsAtPosition(Vector(x, y, z), 2.0, objs, cargos);
		return objs.Count();
	}

	// Raycast vertical descendente (RaycastRVProxy y RayCastBullet): el impacto mas alto entre yFrom e yTo.
	void RayDown(float x, float z, float yFrom, float yTo, out bool hit, out float hitY, out string hitClass)
	{
		hit = false;
		hitY = 0.0;
		hitClass = "";
		vector beg = Vector(x, yFrom, z);
		vector end = Vector(x, yTo, z);
		RaycastRVParams rvParams = new RaycastRVParams(beg, end, null, 0.0);
		rvParams.type = ObjIntersectView;
		ref array<ref RaycastRVResult> results = new array<ref RaycastRVResult>();
		DayZPhysics.RaycastRVProxy(rvParams, results);
		int i = 0;
		while (i < results.Count())
		{
			RaycastRVResult rr = results.Get(i);
			if (rr && rr.obj && (!hit || rr.pos[1] > hitY))
			{
				hit = true;
				hitY = rr.pos[1];
				g_Game.ObjectGetType(rr.obj, hitClass);
			}
			i = i + 1;
		}
		Object bulletObj = null;
		vector bulletPos;
		vector bulletNormal;
		float bulletFraction;
		PhxInteractionLayers mask = PhxInteractionLayers.BUILDING | PhxInteractionLayers.ROADWAY;
		if (DayZPhysics.RayCastBullet(beg, end, mask, null, bulletObj, bulletPos, bulletNormal, bulletFraction))
		{
			if (!hit || bulletPos[1] > hitY)
			{
				hit = true;
				hitY = bulletPos[1];
				hitClass = "";
				if (bulletObj)
				{
					g_Game.ObjectGetType(bulletObj, hitClass);
				}
			}
		}
		hitClass = Clip(hitClass);
	}

	void DoPlaceGround(DSBX_QA_Args args, DSBX_QA_Result res, string fault)
	{
		string pointId;
		string classId;
		float reqX;
		float reqZ;
		if (!GetStr(args, "point_id", pointId) || pointId == "" || !GetStr(args, "class_id", classId) || classId == "")
		{
			Reject(res, "bad_args");
			return;
		}
		if (!GetNum(args, "req_x_m", reqX) || !GetNum(args, "req_z_m", reqZ) || !m_Probe.IsFiniteF(reqX) || !m_Probe.IsFiniteF(reqZ))
		{
			Reject(res, "bad_args");
			return;
		}
		World world = g_Game.GetWorld();
		if (!world)
		{
			res.status = "error";
			res.reason = "world_unavailable";
			return;
		}
		float worldSize = world.GetWorldSize();
		int flags = ECE_NOLIFETIME | ECE_NOPERSISTENCY_WORLD | ECE_PLACE_ON_SURFACE;
		int seqPre = m_SpawnSeqN;
		string decision = "placed";
		string reasonId = "";
		float terrainY = 0.0;
		float roadY = 0.0;
		bool rayHit = false;
		float hitY = 0.0;
		string hitClass = "";
		string obsClass = "";
		int entId = 0;
		vector obsPos = "0 0 0";
		float bboxMinY = 0.0;
		float bboxMaxY = 0.0;
		float obsSurfY = 0.0;
		int preCount = 0;
		int postCount = 0;
		Object obj;
		if (OutOfMap(reqX, reqZ, worldSize))
		{
			decision = "rejected";
			reasonId = "out_of_map";
			if (fault == "spawn_then_reject")
			{
				obj = SpawnTrackedObject(classId, Vector(reqX, 0.0, reqZ), flags, entId, obsClass, obsPos, bboxMinY, bboxMaxY);
				if (obj)
				{
					obsSurfY = g_Game.SurfaceY(obsPos[0], obsPos[2]);
					g_Game.ObjectDelete(obj);
				}
			}
		}
		else
		{
			terrainY = g_Game.SurfaceY(reqX, reqZ);
			roadY = g_Game.SurfaceRoadY(reqX, reqZ);
			RayDown(reqX, reqZ, terrainY + 100.0, terrainY + 0.25, rayHit, hitY, hitClass);
			preCount = CountAt(reqX, terrainY, reqZ);
			bool elevated = (roadY - terrainY > 0.25) || (rayHit && hitY > terrainY + 0.25);
			if (elevated && fault != "ignore_elevated_surface")
			{
				decision = "rejected";
				reasonId = "elevated_surface";
				if (fault == "spawn_then_reject")
				{
					obj = SpawnTrackedObject(classId, Vector(reqX, terrainY, reqZ), flags, entId, obsClass, obsPos, bboxMinY, bboxMaxY);
					if (obj)
					{
						obsSurfY = g_Game.SurfaceY(obsPos[0], obsPos[2]);
						g_Game.ObjectDelete(obj);
					}
				}
			}
			else
			{
				obj = SpawnTrackedObject(classId, Vector(reqX, terrainY, reqZ), flags, entId, obsClass, obsPos, bboxMinY, bboxMaxY);
				if (!obj)
				{
					decision = "rejected";
					reasonId = "spawn_failed";
				}
				else
				{
					obj.SetPosition(Vector(reqX, terrainY - bboxMinY, reqZ));
					obsPos = obj.GetPosition();
					vector obsBox[2];
					obj.ClippingInfo(obsBox);
					bboxMinY = obsBox[0][1];
					bboxMaxY = obsBox[1][1];
					obsSurfY = g_Game.SurfaceY(obsPos[0], obsPos[2]);
					g_Game.ObjectDelete(obj);
					if (m_Probe.AbsF(obsPos[1] + bboxMinY - obsSurfY) >= 0.2)
					{
						decision = "rejected";
						reasonId = "contact_height_error";
					}
				}
			}
			postCount = CountAt(reqX, terrainY, reqZ);
		}
		int seqPost = m_SpawnSeqN;
		res.status = "done";
		res.reason = "";
		res.read.has.Insert("payload");
		AddS(res, "point_id", Clip(pointId));
		AddS(res, "decision_id", decision);
		AddS(res, "reject_reason_id", reasonId);
		AddS(res, "hit_class_id", hitClass);
		AddS(res, "obs_class_id", Clip(obsClass));
		AddN(res, "req_x_m", reqX);
		AddN(res, "req_z_m", reqZ);
		AddN(res, "terrain_y_m", terrainY);
		AddN(res, "road_y_m", roadY);
		AddN(res, "ray_hit_b", BoolF(rayHit));
		AddN(res, "hit_y_m", hitY);
		AddN(res, "seq_pre_n", seqPre);
		AddN(res, "seq_post_n", seqPost);
		AddN(res, "ent_id_n", entId);
		AddN(res, "obs_x_m", obsPos[0]);
		AddN(res, "obs_y_m", obsPos[1]);
		AddN(res, "obs_z_m", obsPos[2]);
		AddN(res, "bbox_min_y_m", bboxMinY);
		AddN(res, "bbox_max_y_m", bboxMaxY);
		AddN(res, "obs_surf_y_m", obsSurfY);
		AddN(res, "pre_count_n", preCount);
		AddN(res, "post_count_n", postCount);
		AddN(res, "tick_ms", m_Probe.NowMs());
		AddN(res, "frame", m_Probe.m_Frame);
	}
}
