# -*- coding: utf-8
# pylint: disable=line-too-long
"""Generate a metabolic reaction network from gene annotations."""

import os
import pandas as pd

from argparse import Namespace
from typing import Dict, List, Tuple

import anvio.terminal as terminal

from anvio.errors import ConfigError
from anvio.utils import is_contigs_db
from anvio.dbops import ContigsSuperclass
from anvio import __file__ as ANVIO_PATH, __version__ as VERSION


__author__ = "Developers of anvi'o (see AUTHORS.txt)"
__copyright__ = "Copyleft 2015-2023, the Meren Lab (http://merenlab.org/)"
__credits__ = []
__license__ = "GPL 3.0"
__version__ = VERSION
__maintainer__ = "Samuel Miller"
__email__ = "samuelmiller10@gmail.com"
__status__ = "Development"


run_quiet = terminal.Run(verbose=False)


class ModelSEEDCompound:
    """Representation of a chemical in the network, with properties given by the ModelSEED Biochemistry database."""
    def __init__(self) -> None:
        self.modelseed_id: str = None
        self.modelseed_name: str = None
        self.kegg_id_aliases: Tuple[str] = None
        self.charge: int = None
        self.formula: str = None

class ModelSEEDReaction:
    """Representation of a reaction in the network, with properties given by the ModelSEED Biochemistry database."""
    def __init__(self) -> None:
        self.modelseed_id: str = None
        self.modelseed_name: str = None
        self.kegg_id_aliases: Tuple[str] = None
        self.ec_number_aliases: Tuple[str] = None
        # compounds, coefficients, and compartments have corresponding elements
        self.compounds: Tuple[ModelSEEDCompound] = None
        self.coefficients: Tuple[int] = None
        self.compartments: Tuple[str] = None
        self.reversibility: bool = None

class KO:
    """Representation of a KEGG Ortholog in the network."""
    def __init__(self) -> None:
        self.id: str = None
        self.name: str = None
        # map *ModelSEED reaction ID* to *ModelSEED reaction object or reaction aliases* in the
        # following dictionaries
        self.reactions: Dict[str, ModelSEEDReaction] = {}
        # Record the KEGG REACTION IDs *encoded by the KO* that are aliases of the ModelSEED
        # reaction ID. These could be a subset of the KEGG reaction aliases of the ModelSEED
        # reaction. The same is true of EC numbers.
        self.kegg_reaction_aliases: Dict[str, Tuple[str]] = {}
        self.ec_number_aliases: Dict[str, Tuple[str]] = {}

class Gene:
    """Representation of a gene in the metabolic network."""
    def __init__(self) -> None:
        self.gcid: int = None
        # KOs matching the gene
        self.kos: List[KO] = []
        # record the strength of each KO match
        self.e_values: List[float] = []

class SingleGenomeNetwork:
    """A reaction network predicted from the KEGG and ModelSEED annotations of a single genome."""
    def __init__(self) -> None:
        # map gcid to gene object
        self.genes: Dict[int, Gene] = {}
        # map KO ID to KO object
        self.kos: Dict[int, KO] = {}
        # map ModelSEED reaction ID to reaction object
        self.reactions: Dict[str, ModelSEEDReaction] = {}
        # map ModelSEED compound ID to compound object
        self.metabolites: Dict[str, ModelSEEDCompound] = {}

class KEGGDatabase:
    """The KEGG KO and REACTION databases set up by anvi'o."""
    default_dir = os.path.join(os.path.dirname(ANVIO_PATH), 'data/MISC/PROTEIN_DATA/kegg')

    def __init__(self) -> None:
        # The KO and reaction tables are derived from the downloaded definition files. They
        # facilitate the lookup of KO IDs, names, EC numbers, and KEGG reactions.
        self.ko_table: pd.DataFrame = None
        self.reaction_table: pd.DataFrame = None

    def load(self, db_dir: str = None) -> None:
        """Load KO and reaction tables from the data directory."""
        if db_dir:
            if not os.path.isdir(db_dir):
                raise ConfigError(f"The provided KEGG database directory, '{db_dir}', was not recognized as a directory.")
        else:
            db_dir = self.default_dir
        ko_data_path = os.path.join(db_dir, 'ko_data.tsv')
        if not os.path.isfile(ko_data_path):
            raise ConfigError(f"The KO data table, 'ko_data.tsv', was not found in the database directory, '{db_dir}'.")
        reaction_data_path = os.path.join(db_dir, 'reaction_data.tsv')
        if not os.path.isfile(reaction_data_path):
            raise ConfigError(f"The KEGG REACTION data table, 'reaction_data.tsv', was not found in the database directory, '{db_dir}'.")

        self.ko_table = pd.read_csv(ko_data_path, sep='\t', header=0, index_col=0, low_memory=False)
        self.reaction_table = pd.read_csv(reaction_data_path, sep='\t', header=0, index_col=0, low_memory=False)

class ModelSEEDDatabase:
    """The ModelSEED Biochemistry database set up by anvi'o."""
    default_dir = os.path.join(os.path.dirname(ANVIO_PATH), 'data/MISC/PROTEIN_DATA/modelseed')

    def __init__(self) -> None:
        # The KEGG and EC tables are rearrangements of the ModelSEED reactions table facilitating
        # lookup of reaction data by KEGG REACTION ID or EC number rather than ModelSEED reaction ID.
        self.kegg_reactions_table: pd.DataFrame = None
        self.ec_reactions_table: pd.DataFrame = None
        self.compounds_table: pd.DataFrame = None

    def load(self, db_dir: str = None) -> None:
        """Load and set up reaction and compound tables from the data directory."""
        if db_dir:
            if not os.path.isdir(db_dir):
                raise ConfigError(f"The provided ModelSEED database directory, '{db_dir}', was not recognized as a directory.")
        else:
            db_dir = self.default_dir
        reactions_path = os.path.join(db_dir, 'reactions.tsv')
        if not os.path.isfile(reactions_path):
            raise ConfigError(f"The ModelSEED reactions table, 'reactions.tsv', was not found in the database directory, '{db_dir}'.")
        compounds_path = os.path.join(db_dir, 'compounds.tsv')
        if not os.path.isfile(compounds_path):
            raise ConfigError(f"The ModelSEED compounds table, 'compounds.tsv', was not found in the database directory, '{db_dir}'.")

        reactions_table = pd.read_csv(reactions_path, sep='\t', header=0, low_memory=False)
        self.compounds_table = pd.read_csv(compounds_path, sep='\t', header=0, index_col='id', low_memory=False)

        # Reorganize the reactions table to facilitate lookup of reaction data by KEGG REACTION ID.
        # Remove reactions without KEGG aliases.
        reactions_table_without_na = reactions_table.dropna(subset=['KEGG'])
        expanded = []
        ko_id_col = []
        for ko_ids, row in zip(
            reactions_table_without_na['KEGG'],
            reactions_table_without_na.itertuples(index=False)
        ):
            ko_ids: str
            # A ModelSEED reaction can have multiple KEGG aliases.
            for ko_id in ko_ids.split('; '):
                ko_id_col.append(ko_id)
                expanded.append(row)
        kegg_reactions_table = pd.DataFrame(expanded)
        kegg_reactions_table['KEGG_REACTION_ID'] = ko_id_col
        self.kegg_reactions_table = kegg_reactions_table

        # Reorganize the reactions table to facilitate lookup of reaction data by EC number.
        # Remove reactions without EC number aliases.
        reactions_table_without_na = reactions_table.dropna(subset=['ec_numbers'])
        expanded = []
        ec_number_col = []
        for ec_numbers, row in zip(
            reactions_table_without_na['ec_numbers'],
            reactions_table_without_na.itertuples(index=False)
        ):
            ec_numbers: str
            # A ModelSEED reaction can have multiple EC number aliases.
            for ec_number in ec_numbers.split('|'):
                ec_number_col.append(ec_number)
                expanded.append(row)
        ec_reactions_table = pd.DataFrame(expanded)
        ec_reactions_table['EC_number'] = ec_number_col
        self.ec_reactions_table = ec_reactions_table

class Constructor:
    """
    Construct a metabolic reaction network within an anvi'o database.

    This currently depends on KEGG annotations of genes and the ModelSEED Biochemistry database.
    """
    # Compounds are identified as cytosolic or extracellular in ModelSEED reactions.
    compartment_ids = {0: 'c', 1: 'e'}

    def __init__(
        self,
        kegg_dir: str,
        modelseed_dir: str,
        run: terminal.Run = terminal.Run(),
        progress: terminal.Progress = terminal.Progress()
    ) -> None:
        self.kegg_dir = kegg_dir
        self.modelseed_dir = modelseed_dir
        self.run = run
        self.progress = progress

        self.kegg_db = KEGGDatabase()
        self.kegg_db.load(self.kegg_dir)
        self.modelseed_db = ModelSEEDDatabase()
        self.modelseed_db.load(self.modelseed_dir)

    def make_single_genome_network(self, contigs_db_path: str):
        contigs_super = self._load_contigs_db(contigs_db_path)

        self.progress.new("Building reaction network")
        self.progress.update("...")

        network = SingleGenomeNetwork()

        self.progress.end()
    def _load_contigs_db(contigs_db_path: str) -> ContigsSuperclass:
        is_contigs_db(contigs_db_path)
        args = Namespace()
        args.contigs_db = contigs_db_path
        contigs_super = ContigsSuperclass(args, r=run_quiet)
        contigs_super.init_functions(requested_sources=['KOfam'])
        return contigs_super

    def _get_modelseed_reaction(self, modelseed_reaction_data: Dict) -> Tuple[ModelSEEDReaction, List[str]]:
        """
        Create a ModelSEED reaction object from its entry in the ModelSEED table.

        Do not populate the reaction object with metabolite objects. Return both the new reaction
        object and a list of associated ModelSEED compound IDs.
        """
        stoichiometry: str = modelseed_reaction_data['stoichiometry']
        if pd.isna(stoichiometry):
            # ignore any reaction lacking a chemical equation for some reason
            return None, None

        reaction = ModelSEEDReaction()

        modelseed_id = modelseed_reaction_data['id']
        if pd.isna(modelseed_id):
            raise ConfigError(
                "The row for the reaction in the ModelSEED table does not but should have an ID. "
                f"Here is the data in the row: '{modelseed_reaction_data}'"
            )
        reaction.modelseed_id = modelseed_id

        modelseed_name = modelseed_reaction_data['name']
        if pd.isna(modelseed_name):
            reaction.modelseed_name = None
        else:
            reaction.modelseed_name = modelseed_name

        kegg_reaction_ids: str = modelseed_reaction_data['KEGG']
        if pd.isna(kegg_reaction_ids):
            reaction.kegg_id_aliases = []
        else:
            reaction.kegg_id_aliases = kegg_reaction_ids.split('; ')

        ec_numbers: str = modelseed_reaction_data['ec_numbers']
        if pd.isna(ec_numbers):
            reaction.ec_number_aliases = []
        else:
            reaction.ec_number_aliases = ec_numbers.split('|')

        reversibility = modelseed_reaction_data['reversibility']
        if pd.isna(reversibility):
            raise ConfigError(
                "The row for the reaction in the ModelSEED table was expected to have a 'reversibility' value. "
                f"Here is the data in the row: '{modelseed_reaction_data}'"
            )
        if reversibility == '=' or reversibility == '?':
            # Assume that reactions lacking data ('?') are reversible.
            reaction.reversibility = True
        else:
            reaction.reversibility = False

        decimal_reaction_coefficients = []
        split_stoichiometry = stoichiometry.split(';')
        modelseed_compound_ids = []
        compartments = []
        for entry in split_stoichiometry:
            split_entry = entry.split(':')
            decimal_reaction_coefficients.append(split_entry[0])
            modelseed_compound_ids.append(split_entry[1])
            compartments.append(self.compartment_ids[int(split_entry[2])])
        reaction.compartments = tuple(compartments)
        reaction_coefficients = self._to_lcm_denominator(decimal_reaction_coefficients)
        direction = modelseed_reaction_data['direction']
        if pd.isna(direction):
            raise ConfigError(
                "The row for the reaction in the ModelSEED table was expected to have a 'direction' value. "
                f"Here is the data in the row: '{modelseed_reaction_data}'"
            )
        if (direction == '>' and reversibility == '<') or (direction == '<' and reversibility == '>'):
            # The way the reaction is written is the opposite of the way the reaction proceeds.
            reaction_coefficients = [-c for c in reaction_coefficients]
        reaction.coefficients = tuple(reaction_coefficients)

        return reaction, modelseed_compound_ids

    def _to_lcm_denominator(self, floats) -> Tuple[int]:
        def lcm(a, b):
            return a * b // gcd(a, b)
        rationals = [Fraction(f).limit_denominator() for f in floats]
        lcm_denom = reduce(lcm, [r.denominator for r in rationals])
        return tuple(int(r.numerator * lcm_denom / r.denominator) for r in rationals)

    def _get_modelseed_compound(self, modelseed_compound_data: Dict) -> ModelSEEDCompound:
        compound = ModelSEEDCompound()
        compound.modelseed_id = modelseed_compound_data['id']

        modelseed_name = modelseed_compound_data['name']
        if pd.isna(modelseed_name):
            compound.modelseed_name = None
        else:
            compound.modelseed_name = modelseed_name

        kegg_id_aliases: str = modelseed_compound_data['KEGG']
        if pd.isna(kegg_id_aliases):
            compound.kegg_id_aliases = []
        else:
            compound.kegg_id_aliases = kegg_id_aliases.split('; ')

        formula = modelseed_compound_data['formula']
        if pd.isna(formula):
            compound.formula = None
            # compounds without formulas have a nominal charge of 10000000 in compounds.tsv
            compound.charge = None
        else:
            compound.formula = formula
            charge = modelseed_compound_data['charge']
            if pd.isna(charge):
                raise ConfigError(
                    f"The charge of a ModelSEED compound, '{compound.modelseed_id}', was not recorded "
                    "in 'compounds.tsv' but is expected to be present as an integer. Here is the data "
                    f"in the row for the compound: '{modelseed_compound_data}'"
                )
            compound.charge = charge

        return compound
