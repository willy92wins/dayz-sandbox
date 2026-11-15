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
	ref array<string> m_Pages;

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
		m_Pages = new array<string>();
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
		m_Pages = new array<string>();
	}

	bool FitsCurrentPage()
	{
		string candidate = DSBX_Wire.CatalogPageBody(m_CatalogId, 99999, 99999, m_Build, m_ModsetHash, m_CurClasses, m_CurBases);
		if (candidate == "")
		{
			return false;
		}
		return candidate.Length() <= DSBX_WIRE_CAP;
	}

	void FlushCurrentPage()
	{
		m_PageClasses.Insert(m_CurClasses);
		m_PageBases.Insert(m_CurBases);
		m_CurClasses = new array<string>();
		m_CurBases = new array<string>();
	}

	void AddClassPair(string clsName, string baseName)
	{
		if (DSBX_Wire.WireId(clsName) == "" || DSBX_Wire.WireId(baseName) == "")
		{
			m_SkippedCount = m_SkippedCount + 1;
			return;
		}
		m_CurClasses.Insert(clsName);
		m_CurBases.Insert(baseName);
		if (FitsCurrentPage())
		{
			return;
		}
		int last = m_CurClasses.Count() - 1;
		m_CurClasses.RemoveOrdered(last);
		m_CurBases.RemoveOrdered(last);
		if (m_CurClasses.Count() == 0)
		{
			m_SkippedCount = m_SkippedCount + 1;
			return;
		}
		FlushCurrentPage();
		m_CurClasses.Insert(clsName);
		m_CurBases.Insert(baseName);
		if (!FitsCurrentPage())
		{
			m_CurClasses.RemoveOrdered(0);
			m_CurBases.RemoveOrdered(0);
			m_SkippedCount = m_SkippedCount + 1;
		}
	}

	void FinalizePages()
	{
		if (m_CurClasses.Count() > 0 || m_PageClasses.Count() == 0)
		{
			FlushCurrentPage();
		}
		int totalPages = m_PageClasses.Count();
		int p = 0;
		while (p < totalPages)
		{
			string body = DSBX_Wire.CatalogPageBody(m_CatalogId, p + 1, totalPages, m_Build, m_ModsetHash, m_PageClasses.Get(p), m_PageBases.Get(p));
			m_Pages.Insert(body);
			p = p + 1;
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
			if (scope == 2)
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
		return m_Pages.Count();
	}

	string GetPage(int idx)
	{
		return m_Pages.Get(idx);
	}
}
