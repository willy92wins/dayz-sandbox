class CfgPatches
{
	class DayZSandbox_QA_Expansion
	{
		units[] = {};
		weapons[] = {};
		requiredVersion = 0.1;
		requiredAddons[] = {"DZ_Data", "DZ_Characters", "DayZSandbox_QA", "DayZExpansion_Core_Scripts", "DayZExpansion_AI_Scripts"};
	};
};

class CfgMods
{
	class DayZSandbox_QA_Expansion
	{
		dir = "DayZSandbox_QA_Expansion";
		name = "DayZSandbox_QA_Expansion";
		type = "mod";
		dependencies[] = {"World", "Mission"};
		class defs
		{
			class worldScriptModule
			{
				value = "";
				files[] = {"DayZSandbox_QA_Expansion/scripts/4_World"};
			};
			class missionScriptModule
			{
				value = "";
				files[] = {"DayZSandbox_QA_Expansion/scripts/5_Mission"};
			};
		};
	};
};
