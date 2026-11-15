class CfgPatches
{
	class DayZSandbox_QA
	{
		units[] = {};
		weapons[] = {};
		requiredVersion = 0.1;
		requiredAddons[] = {"DZ_Data"};
	};
};

class CfgMods
{
	class DayZSandbox_QA
	{
		dir = "DayZSandbox_QA";
		name = "DayZSandbox_QA";
		type = "mod";
		dependencies[] = {"World", "Mission"};
		class defs
		{
			class worldScriptModule
			{
				value = "";
				files[] = {"DayZSandbox_QA/scripts/4_World"};
			};
			class missionScriptModule
			{
				value = "";
				files[] = {"DayZSandbox_QA/scripts/5_Mission"};
			};
		};
	};
};
