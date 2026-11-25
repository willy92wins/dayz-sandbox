class DSBX_Catalog
{
	string m_CatalogId;
	string m_Build;
	string m_ModsetHash;
	int m_TotalCfg;
	int m_ScanIdx;
	int m_SkippedCount;
	bool m_ScanStarted;
	bool m_ScanDone;
	bool m_ScanLogged;
	ref array<string> m_CurClasses;
	ref array<string> m_CurBases;
	ref array<ref array<string>> m_PageClasses;
	ref array<ref array<string>> m_PageBases;
	int m_EmptyPageBytes;
	int m_CurBytes;

	void DSBX_Catalog()
	{
		m_CatalogId = "";
		m_Build = "";
		m_ModsetHash = "";
		m_TotalCfg = 0;
		m_ScanIdx = 0;
		m_SkippedCount = 0;
		m_ScanStarted = false;
		m_ScanDone = false;
		m_ScanLogged = false;
		m_CurClasses = new array<string>();
		m_CurBases = new array<string>();
		m_PageClasses = new array<ref array<string>>();
		m_PageBases = new array<ref array<string>>();
		m_EmptyPageBytes = 0;
		m_CurBytes = 0;
	}

	void StartScan(string buildStr, array<string> sortedModset)
	{
		string fullUuid = DSBX_Wire.MakeUuid32();
		m_CatalogId = fullUuid.Substring(0, 16);
		m_Build = buildStr;
		m_ModsetHash = DSBX_Wire.ModsetHash(sortedModset);
		m_TotalCfg = 0;
		if (g_Game)
		{
			m_TotalCfg = g_Game.ConfigGetChildrenCount("CfgVehicles");
		}
		m_ScanIdx = 0;
		m_SkippedCount = 0;
		m_ScanStarted = true;
		m_ScanDone = false;
		m_ScanLogged = false;
		m_CurClasses = new array<string>();
		m_CurBases = new array<string>();
		m_PageClasses = new array<ref array<string>>();
		m_PageBases = new array<ref array<string>>();
		// tamano de una pagina vacia con los marcadores de 5 cifras: las paginas reales nunca miden mas
		m_EmptyPageBytes = 0;
		array<string> noClasses = new array<string>();
		array<string> noBases = new array<string>();
		string emptyBody = DSBX_Wire.CatalogPageBody(m_CatalogId, 99999, 99999, m_Build, m_ModsetHash, noClasses, noBases);
		if (emptyBody != "")
		{
			m_EmptyPageBytes = emptyBody.Length();
		}
		m_CurBytes = m_EmptyPageBytes;
	}

	// Bytes que anade [cls,base] a la pagina: dos pares de comillas, corchetes y la coma interna (7),
	// mas la coma que lo separa del anterior. WireId solo admite ASCII sin escape.
	int PairBytes(string clsName, string baseName, bool first)
	{
		int n = clsName.Length() + baseName.Length() + 7;
		if (!first)
		{
			n = n + 1;
		}
		return n;
	}

	void FlushCurrentPage()
	{
		m_PageClasses.Insert(m_CurClasses);
		m_PageBases.Insert(m_CurBases);
		m_CurClasses = new array<string>();
		m_CurBases = new array<string>();
		m_CurBytes = m_EmptyPageBytes;
	}

	void AddClassPair(string clsName, string baseName)
	{
		string clsWire = DSBX_Wire.WireId(clsName);
		string baseWire = DSBX_Wire.WireId(baseName);
		if (m_EmptyPageBytes <= 0 || clsWire == "" || baseWire == "")
		{
			m_SkippedCount = m_SkippedCount + 1;
			return;
		}
		int add = PairBytes(clsName, baseName, m_CurClasses.Count() == 0);
		if (m_CurBytes + add > DSBX_WIRE_CAP && m_CurClasses.Count() > 0)
		{
			FlushCurrentPage();
			add = PairBytes(clsName, baseName, true);
		}
		if (m_CurBytes + add > DSBX_WIRE_CAP)
		{
			m_SkippedCount = m_SkippedCount + 1;
			return;
		}
		m_CurClasses.Insert(clsName);
		m_CurBases.Insert(baseName);
		m_CurBytes = m_CurBytes + add;
	}

	void FinalizePages()
	{
		if (m_CurClasses.Count() > 0 || m_PageClasses.Count() == 0)
		{
			FlushCurrentPage();
		}
		m_ScanDone = true;
	}

	bool TickScan()
	{
		if (!m_ScanStarted || m_ScanDone)
		{
			return m_ScanDone;
		}
		int steps = 0;
		while (m_ScanIdx < m_TotalCfg && steps < DSBX_Const.CATALOG_SCAN_BATCH)
		{
			string clsName = "";
			g_Game.ConfigGetChildName("CfgVehicles", m_ScanIdx, clsName);
			m_ScanIdx = m_ScanIdx + 1;
			steps = steps + 1;
			int scope = g_Game.ConfigGetInt("CfgVehicles " + clsName + " scope");
			if (scope >= 1)
			{
				string baseName = "";
				g_Game.ConfigGetBaseName("CfgVehicles " + clsName, baseName);
				AddClassPair(clsName, baseName);
			}
		}
		if (m_ScanIdx >= m_TotalCfg)
		{
			FinalizePages();
		}
		return m_ScanDone;
	}

	bool IsScanDone()
	{
		return m_ScanDone;
	}

	bool ConsumeScanLogPending()
	{
		if (m_ScanDone && !m_ScanLogged)
		{
			m_ScanLogged = true;
			return true;
		}
		return false;
	}

	int GetSkippedCount()
	{
		return m_SkippedCount;
	}

	int GetPageCount()
	{
		if (!m_ScanDone)
		{
			return 0;
		}
		return m_PageClasses.Count();
	}

	// Se construye al enviarla: el trabajo se reparte entre envios y no cae entero en un tick.
	string GetPage(int idx)
	{
		return DSBX_Wire.CatalogPageBody(m_CatalogId, idx + 1, m_PageClasses.Count(), m_Build, m_ModsetHash, m_PageClasses.Get(idx), m_PageBases.Get(idx));
	}
}
