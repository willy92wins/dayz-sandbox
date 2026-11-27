class CfgPatches
{
	class DayZSandbox_Expansion
	{
		units[] = {};
		weapons[] = {};
		requiredVersion = 0.1;
		requiredAddons[] = {"DZ_Data", "DZ_Characters", "DayZSandbox", "DayZExpansion_Core_Scripts", "DayZExpansion_AI_Scripts"};
	};
};

class CfgMods
{
	class DayZSandbox_Expansion
	{
		dir = "DayZSandbox_Expansion";
		name = "DayZSandbox_Expansion";
		type = "mod";
		dependencies[] = {"World", "Mission"};
		class defs
		{
			class worldScriptModule
			{
				value = "";
				files[] = {"DayZSandbox_Expansion/scripts/4_World"};
			};
			class missionScriptModule
			{
				value = "";
				files[] = {"DayZSandbox_Expansion/scripts/5_Mission"};
			};
		};
	};
};
