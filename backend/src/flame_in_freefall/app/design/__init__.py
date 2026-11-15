"""Phase 2 "design your system" layer: environments, safety controls, Earth applications, PSI media, exploratory
simulators, data export and a tool-using assistant.

Every module reads the PUBLIC export only and never writes to it. Rules carried over from M1-M7:
* nothing automatic is presented as scientifically confirmed; draft/provisional/exploratory states travel with data;
* units, conditions and gravity are never imputed; missing values stay ``unknown`` (never ``outside``);
* ``overlaps`` is not coverage; predictions come from tools (never from the language model) and are exploratory.
"""
