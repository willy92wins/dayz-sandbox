class CfgPatches
{
	class DayZSandbox
	{
		units[] = {};
		weapons[] = {};
		requiredVersion = 0.1;
		requiredAddons[] = {"DZ_Data"};
	};
};

class CfgMods
{
	class DayZSandbox
	{
		dir = "DayZSandbox";
		name = "DayZSandbox";
		type = "mod";
		dependencies[] = {"Game", "Mission"};
		class defs
		{
			class gameScriptModule
			{
				value = "";
				files[] = {"DayZSandbox/scripts/3_Game"};
			};
			class missionScriptModule
			{
				value = "";
				files[] = {"DayZSandbox/scripts/5_Mission"};
			};
		};
	};
};
