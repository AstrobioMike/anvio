# -*- coding: utf-8
# pylint: disable=line-too-long
"""Generate a metabolic reaction network from gene annotations."""

import os
import re
import glob
import math
import time
import shutil
import hashlib
import tarfile
import zipfile
import argparse
import fractions
import functools
import collections
import numpy as np
import pandas as pd
import multiprocessing as mp

from typing import Dict, List, Tuple

import anvio.utils as utils
import anvio.tables as tables
import anvio.terminal as terminal

from anvio.errors import ConfigError
from anvio.dbops import ContigsDatabase
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

class GeneCluster:
    """Representation of a gene cluster."""
    def __init__(self) -> None:
        # genes in the gene cluster
        self.genes: List[Gene] = []

class Bin:
    """Representation of a bin of genes or gene clusters."""
    pass

class GeneBin(Bin):
    """Representation of a bin of genes."""
    def __init__(self) -> None:
        self.genes: List[Gene] = []

class GeneClusterBin(Bin):
    """Representation of a bin of gene clusters."""
    def __init__(self) -> None:
        self.gene_clusters: List[GeneCluster] = []

class BinCollection:
    """Representation of a collection of bins."""
    def __init__(self) -> None:
        self.bins: List[Bin] = []

class ReactionNetwork:
    """A reaction network predicted from KEGG KO and ModelSEED annotations."""
    def __init__(self) -> None:
        # map KO ID to KO object
        self.kos: Dict[int, KO] = {}
        # map ModelSEED reaction ID to reaction object
        self.reactions: Dict[str, ModelSEEDReaction] = {}
        # map ModelSEED compound ID to compound object
        self.metabolites: Dict[str, ModelSEEDCompound] = {}
        # map KEGG REACTION ID to ModelSEED reaction IDs
        self.kegg_reactions: Dict[str, List[str]] = {}
        # map EC number to ModelSEED reaction IDs
        self.ec_numbers: Dict[str, List[str]] = {}

class GenomicNetwork(ReactionNetwork):
    """A reaction network predicted from KEGG KO and ModelSEED annotations of genes."""
    def __init__(self) -> None:
        # map gene caller ID to gene object
        self.genes: Dict[int, Gene] = {}
        self.bins: Dict[str, GeneBin] = {}
        self.collection: BinCollection = None
        super().__init__()

    def export_json(
        self,
        path: str,
        annotate_genes: tuple = ('bin', ),
        annotate_reactions: tuple = ('bin', 'kegg_reaction', 'ec_number'),
        annotate_metabolites: tuple = ('bin', 'kegg_compound'),
        run: terminal.Run = terminal.Run(),
        progress: terminal.Progress = terminal.Progress()
    ) -> None:
        """
        Export the network to a metabolic model file in JSON format.

        Parameters
        ==========
        path : str
            output JSON file path

        annotate_genes : tuple, ('bin', )
            Annotate gene entries in the JSON file with additional data, selecting from the following:

            'bin' : bins in which the gene occurs

            'all_ko' : all KOs associated with the gene

            'ko' : KOs associated with the gene that yielded reactions in the network

            'ko_e_value' : scores of KO associations with the gene; if 'all_ko' is provided, then
                each value corresponds to a KO in 'all_ko', whereas if only 'ko' is provided, then each
                value corresponds to a KO in 'ko'

        annotate_reactions : tuple, ('bin', 'kegg_reaction', 'ec_number')
            Annotate reaction entries in the JSON file with additional data, selecting from the following:

            'bin' : bins in which the reaction occurs

            'kegg_reaction' : KO-associated KEGG reaction IDs yielding the ModelSEED reaction

            'ec_number' : KO-associated EC numbers yielding the ModelSEED reaction

            'ko' : KOs yielding the ModelSEED reaction

        annotate_metabolites : tuple, ('bin', 'kegg_compound')
            Annotate metabolite entries in the JSON file with additional data, selecting from the following:

            'bin' : bins in which the metabolite occurs

            'kegg_compound' : KEGG compound aliases of the ModelSEED compound

            'ko' : KOs yielding the ModelSEED compound

        run : terminal.Run, terminal.Run()

        progress : terminal.Progress, terminal.Progress()
        """
        pass

class PangenomicNetwork(ReactionNetwork):
    """A reaction network predicted from KEGG KO and ModelSEED annotations of pangenomic gene clusters."""
    def __init__(self) -> None:
        # map gene cluster ID to gene cluster object
        self.gene_clusters: Dict[str, GeneCluster] = {}
        self.bins: Dict[str, GeneClusterBin] = {}
        self.collection: BinCollection = None
        super().__init__()

    def export_json(
        self,
        path: str,
        annotate_genes: tuple = ('genome', 'bin', ),
        annotate_reactions: tuple = ('genome', 'bin', 'kegg_reaction', 'ec_number'),
        annotate_metabolites: tuple = ('genome', 'bin', 'kegg_compound'),
        run: terminal.Run = terminal.Run(),
        progress: terminal.Progress = terminal.Progress()
    ) -> None:
        """
        Export the network to a metabolic model file in JSON format. *Gene entries in this file
        represent gene clusters.* Optionally, gene, reaction, and metabolite entries in this file
        are annotated with the names of genomes and names of gene cluster bins in which they occur.

        Parameters
        ==========
        Parameters
        ==========
        path : str
            output JSON file path

        annotate_genes : tuple, ('genome', 'bin', )
            Annotate gene (cluster) entries in the JSON file with additional data, selecting
            from the following:

            'genome' : genomes in which the genes of the cluster occur

            'bin' : bins in which the gene cluster occurs

            'all_ko' : all KOs associated with genes in the cluster, sorted in descending order of
                the number of genes in the cluster that were associated with each KO and then mean
                e-value of gene-KO assignments

            'ko' : KOs associated with the gene cluster that yielded reactions in the network,
                sorted in descending order of the number of genes in the cluster that were
                associated with each KO and then mean e-value of gene-KO assignments

            'ko_count' : number of genes in the cluster that were associated with each KO; if
                'all_ko' is provided, then each value corresponds to a KO in 'all_ko', whereas if
                only 'ko' is provided, then each value corresponds to a KO in 'ko'

            'e_value' : mean scores of KO associations with genes in the cluster; if 'all_ko' is
                provided, then each value corresponds to a KO in 'all_ko', whereas if only 'ko' is
                provided, then each value corresponds to a KO in 'ko'

        annotate_reactions : tuple, ('genome', 'bin', 'kegg_reaction', 'ec_number')
            Annotate reaction entries in the JSON file with additional data, selecting from the following:

            'genome' : genomes in which the reaction occurs

            'bin' : bins in which the reaction occurs

            'kegg_reaction' : KO-associated KEGG reaction IDs yielding the ModelSEED reaction

            'ec_number' : KO-associated EC numbers yielding the ModelSEED reaction

            'ko' : KOs yielding the ModelSEED reaction

        annotate_metabolites : tuple, ('genome', 'bin', 'kegg_compound')
            Annotate metabolite entries in the JSON file with additional data, selecting from the following:

            'genome' : genomes in which the metabolite occurs

            'bin' : bins in which the metabolite occurs

            'kegg_compound' : KEGG compound aliases of the ModelSEED compound

            'ko' : KOs yielding the ModelSEED compound

        run : terminal.Run, terminal.Run()

        progress : terminal.Progress, terminal.Progress()
        """
        pass

class KEGGDatabase:
    """
    The KEGG KO and REACTION databases set up by anvi'o.

    By default, the databases are loaded from a default directory of KEGG KO and REACTION files
    unless an alternative directory is provided.
    """
    default_dir = os.path.join(os.path.dirname(ANVIO_PATH), 'data/MISC/PROTEIN_DATA/kegg')

    def __init__(self, db_dir: str = None) -> None:
        """
        Load and set up KO and reaction tables derived from downloaded definition files. These
        tables facilitate the lookup of KO IDs and names, EC numbers, and KEGG REACTION IDs.

        Parameters
        ==========
        db_dir : str, None
            Directory of KEGG KO and REACTION files to use instead of the default.
        """
        self.ko_table: pd.DataFrame = None
        self.reaction_table: pd.DataFrame = None
        # The KEGG release is stored in the KO and REACTION info files downloaded at the time of the
        # other database files.
        self.release: str = None

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
        ko_info_path = os.path.join(db_dir, 'ko_info.txt')
        if not os.path.isfile(ko_info_path):
            raise ConfigError(f"The KO info file, 'ko_info.txt', was not found in the database directory, '{db_dir}'.")
        reaction_info_path = os.path.join(db_dir, 'reaction_info.txt')
        if not os.path.isfile(reaction_info_path):
            raise ConfigError(f"The KEGG REACTION info file, 'reaction_info.txt', was not found in the database directory, '{db_dir}'.")

        self.ko_table = pd.read_csv(ko_data_path, sep='\t', header=0, index_col=0, low_memory=False)
        self.reaction_table = pd.read_csv(reaction_data_path, sep='\t', header=0, index_col=0, low_memory=False)

        ko_release = None
        with open(ko_info_path) as f:
            for line in f:
                if line[:2] == 'ko':
                    ko_release = line[2:].strip()
                    break
        assert ko_release is not None
        reaction_release = None
        with open(reaction_info_path) as f:
            for line in f:
                if line[:2] == 'rn':
                    reaction_release = line[2:].strip()
                    break
        assert reaction_release is not None
        assert ko_release == reaction_release
        self.release = ko_release

class ModelSEEDDatabase:
    """
    The ModelSEED Biochemistry database set up by anvi'o.

    By default, the database is loaded from a default directory of ModelSEED files unless an
    alternative directory is provided.
    """
    default_dir = os.path.join(os.path.dirname(ANVIO_PATH), 'data/MISC/PROTEIN_DATA/modelseed')

    # Compounds are identified as cytosolic or extracellular in ModelSEED reactions.
    compartment_ids = {0: 'c', 1: 'e'}

    def __init__(self, db_dir: str = None) -> None:
        """
        Load and set up reaction and compound tables from the data directory.

        Parameters
        ==========
        db_dir : str, None
            Directory of ModelSEED files to use instead of the default.
        """
        # The KEGG and EC tables are rearrangements of the ModelSEED reactions table facilitating
        # lookup of reaction data by KEGG REACTION ID or EC number rather than ModelSEED reaction ID.
        self.kegg_reactions_table: pd.DataFrame = None
        self.ec_reactions_table: pd.DataFrame = None
        self.compounds_table: pd.DataFrame = None
        # The SHA is the git commit hash of the ModelSEED repository, stored in a file when
        # anvi'o downloaded and set up the ModelSEED files.
        self.sha: str = None

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
        sha_path = os.path.join(db_dir, 'sha.txt')
        if not os.path.isfile(sha_path):
            raise ConfigError(f"The file, 'sha.txt', which contains the git commit hash of the ModelSEED database, was not found in the database directory, '{db_dir}'.")

        reactions_table = pd.read_csv(reactions_path, sep='\t', header=0, low_memory=False)
        self.compounds_table = pd.read_csv(compounds_path, sep='\t', header=0, index_col='id', low_memory=False)
        with open(sha_path) as f:
            self.sha = f.readline().strip()

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
    """Construct metabolic reaction network objects."""
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

        self.kegg_db = KEGGDatabase(self.kegg_dir)
        self.modelseed_db = ModelSEEDDatabase(self.modelseed_dir)

    def import_network(self, json: str) -> ReactionNetwork:
        """Import a reaction network from a metabolic model JSON file."""
        pass

    def load_network(
        self,
        contigs_db: str = None,
        genomes_storage_db: str = None,
        pan_db: str = None
    ) -> ReactionNetwork:
        self.check_network(contigs_db=contigs_db, genomes_storage_db=genomes_storage_db, pan_db=pan_db)

    def check_network(
        self,
        contigs_db: str = None,
        genomes_storage_db: str = None,
        pan_db: str = None
    ) -> bool:
        """
        Check that the reaction network stored in a database is derived from the current gene KO
        annotations in the database.

        Parameters
        ==========
        contigs_db : str, None
            Path to a contigs database in which a reaction network is stored.

        genomes_storage_db: str, None
            Path to a genomes storage database in which KO annotations are stored. 'pan_db' is also
            required.

        pan_db: str, None
            Path to a pan database in which a reaction network is stored. 'genomes_storage_db' is
            also required.

        Returns
        =======
        bool
            True if the reaction network is derived from the current gene KO annotations in the
            database, else False.
        """
        return

    def make_network(
        self,
        contigs_db: str = None,
        genomes_storage_db: str = None,
        pan_db: str = None,
        store: bool = True,
        overwrite_existing_network: bool = False
    ) -> ReactionNetwork:
        """
        Make a metabolic reaction network from KEGG Orthologs stored in an anvi'o database,
        associated KEGG annotations, and the ModelSEED Biochemistry database.

        Parameters
        ==========
        contigs_db : str, None
            Path to a contigs database. The database can represent different types of samples,
            including a single genome, metagenome, or transcriptome. The network is derived from
            gene KO annotations stored in the database. If 'store' is True, the network is saved in
            the database.

        genomes_storage_db : str, None
            Path to a genomes storage database. The pangenomic network is derived from gene KO
            annotations stored in the database. 'pan_db' is also required.

        pan_db : str, None
            Path to a pan database. The pangenomic network is determined for gene clusters stored in
            the database. If 'store' is True, the network is saved in the database.
            'genomes_storage_db' is also required.

        store : bool, True
            Save the network. A network constructed from a contigs database is stored in that
            database. A pangenomic network constructed from a genomes stroage database and pan
            database is stored in the pan database.

        overwrite_existing_network : bool, False
            Overwrite an existing network stored in the contigs or pan database. 'store' is also
            required.
        """
        if contigs_db:
            self.run.info_single("A reaction network will be made from protein orthology annotations in the contigs database.")
            network = self.make_contigs_database_network(contigs_db, store=store, overwrite_existing_network=overwrite_existing_network)
        elif genomes_storage_db or pan_db:
            self.run.info_single("A pangenomic reaction network will be made from protein orthology annotations in the genomes storage database and gene clusters in the pan database.")
            network = self.make_pangenomic_network(genomes_storage_db, pan_db, store=store, overwrite_existing_network=overwrite_existing_network)
        else:
            raise ConfigError("A reaction network cannot be made without a database source. Either a contigs database or a genomes storage database and pan database are required.")
        return network

    def make_contigs_database_network(
        self,
        contigs_db: str,
        store: bool = True,
        overwrite_existing_network: bool = False
    ) -> GenomicNetwork:
        """
        Make a metabolic reaction network from KEGG Orthologs stored in a contigs database.

        Parameters
        ==========
        contigs_db : str
            Path to a contigs database. The database can represent different types of samples,
            including a single genome, metagenome, or transcriptome. The network is derived from
            gene KO annotations stored in the database.

        store : bool, True
            Save the network to the contigs database.

        overwrite_existing_network : bool, False
            Overwrite an existing network stored in the contigs database. 'store' is also required.

        Returns
        =======
        GenomicNetwork
            The network derived from the contigs database.
        """
        # Load the contigs database.
        self.run.info("Contigs database", contigs_db)
        utils.is_contigs_db(contigs_db)
        args = argparse.Namespace()
        args.contigs_db = contigs_db
        contigs_super = ContigsSuperclass(args, r=run_quiet)
        if store and contigs_super.a_meta['reaction_network_ko_annotations_hash'] and not overwrite_existing_network:
            raise ConfigError("The existing reaction network in the contigs database must be explicitly overwritten.")
        contigs_super.init_functions(requested_sources=['KOfam'])

        self.progress.new("Building reaction network")
        self.progress.update("...")

        network = GenomicNetwork()

        modelseed_kegg_reactions_table = self.modelseed_db.kegg_reactions_table
        modelseed_ec_reactions_table = self.modelseed_db.ec_reactions_table
        modelseed_compounds_table = self.modelseed_db.compounds_table

        # Record KOs that annotated genes but for some reason are not found in the KO database.
        undefined_ko_ids = []

        # Parse gene-KO matches recorded in the contigs database.
        gene_function_calls_dict: Dict = contigs_super.gene_function_calls_dict
        total_ko_matches = len(gene_function_calls_dict)
        num_ko_matches_parsed = -1
        for gcid, gene_dict in gene_function_calls_dict.items():
            num_ko_matches_parsed += 1
            self.progress.update(f"Gene-KO matches parsed: {num_ko_matches_parsed} / {total_ko_matches}")

            if gcid in network.genes:
                # An object representing the gene was already added to the network.
                gene = network.genes[gcid]
            else:
                gene = Gene()
                gene.gcid = gcid
                # Add the gene to the network, regardless of whether it yields reactions.
                network.genes[gcid] = gene

            ko_data = gene_dict['KOfam']
            gene.e_values.append(float(ko_data[2]))
            ko_id = ko_data[0]
            if ko_id in network.kos:
                # An object representing the KO was already added to the network, and objects
                # representing associated reactions and metabolites were already added as well.
                gene.kos.append(network.kos[ko_id])
                continue
            else:
                ko = KO()
                ko.id = ko_id
                ko.name = ko_data[1]
                gene.kos.append(ko)
                # Add the KO to the network, regardless of whether it yields reactions.
                network.kos[ko_id] = ko

            # Find KEGG reactions and EC numbers associated with the KO.
            try:
                ko_info = self.kegg_db.ko_table.loc[ko.id]
            except KeyError:
                undefined_ko_ids.append(ko_id)
                continue
            ko_kegg_reaction_info: str = ko_info.loc['reactions']
            if pd.isna(ko_kegg_reaction_info):
                # The KO is not associated with KEGG reactions.
                ko_kegg_reaction_ids = []
            else:
                ko_kegg_reaction_ids = ko_kegg_reaction_info.split()
            ko_ec_number_info: str = ko_info.loc['ec_numbers']
            if pd.isna(ko_ec_number_info):
                # The KO is not associated with EC numbers.
                ko_ec_numbers = []
            else:
                ko_ec_numbers = ko_ec_number_info.split()

            if not (ko_kegg_reaction_ids or ko_ec_numbers):
                # ModelSEED reaction objects cannot be defined for the KO in the absence of
                # either KEGG reactions or EC numbers associated with the KO.
                continue

            # Separate KEGG REACTION IDs that have previously been used to create ModelSEEDReaction
            # objects from those that have not.
            unadded_kegg_reaction_ids = []
            for kegg_reaction_id in ko_kegg_reaction_ids:
                if not kegg_reaction_id in network.kegg_reactions:
                    unadded_kegg_reaction_ids.append(kegg_reaction_id)
                    network.kegg_reactions[kegg_reaction_id] = []
                    continue
                # Retrieve the one or more ModelSEED reactions aliased by the KEGG REACTION ID.
                for modelseed_id in network.kegg_reactions[kegg_reaction_id]:
                    reaction = network.reactions[modelseed_id]
                    ko.reactions[modelseed_id] = reaction
                    # Record the KEGG REACTION IDs and EC numbers from the KO that yield the ModelSEED reaction.
                    ko.kegg_reaction_aliases[modelseed_id] = tuple(set(ko_kegg_reaction_ids).intersection(set(reaction.kegg_id_aliases)))
                    ko.ec_number_aliases[modelseed_id] = tuple(set(ko_ec_numbers).intersection(set(reaction.ec_number_aliases)))

            # Separate EC numbers that have previously been used to create ModelSEEDReaction objects
            # from from those that have not.
            unadded_ec_numbers = []
            for ec_number in ko_ec_numbers:
                if not ec_number in network.ec_numbers:
                    unadded_ec_numbers.append(ec_number)
                    network.ec_numbers[ec_number] = []
                    continue
                # Retrieve the one or more ModelSEED reactions aliased by the EC number.
                for modelseed_id in network.ec_numbers[ec_number]:
                    reaction = network.reactions[modelseed_id]
                    if modelseed_id in reaction.ec_number_aliases:
                        # A KEGG REACTION ID associated with the KO was already linked to the
                        # ModelSEED ID, at which point KO EC number aliases were also recorded.
                        # Avoid redundant work linking the ModelSEED reaction to the KO object.
                        continue
                    ko.reactions[modelseed_id] = reaction
                    ko.kegg_reaction_aliases[modelseed_id] = tuple(set(ko_kegg_reaction_ids).intersection(set(reaction.kegg_id_aliases)))
                    ko.ec_number_aliases[modelseed_id] = tuple(set(ko_ec_numbers).intersection(set(reaction.ec_number_aliases)))

            if not (unadded_kegg_reaction_ids or unadded_ec_numbers):
                # All of the KEGG reactions and EC numbers associated with the KO have already been
                # encountered in previously processed KOs and added to the network, so proceed to
                # the next gene KO annotation.
                continue

            # Get data on unencountered ModelSEED reactions aliased by KEGG REACTION IDs and EC
            # numbers.
            modelseed_reactions_data = {}
            if unadded_kegg_reaction_ids:
                # Each row of the table represents a unique KEGG REACTION -> ModelSEED reaction mapping.
                modelseed_kegg_reactions_dict: Dict[str, Dict] = modelseed_kegg_reactions_table[
                    modelseed_kegg_reactions_table['KEGG_REACTION_ID'].isin(unadded_kegg_reaction_ids)
                ].to_dict(orient='index')
                for modelseed_reaction_data in modelseed_kegg_reactions_dict.values():
                    modelseed_reaction_id = modelseed_reaction_data['id']
                    if modelseed_reaction_id in modelseed_reactions_data:
                        # Data on the ModelSEED reaction has already been added to the list using a
                        # different KEGG REACTION ID.
                        continue
                    modelseed_reactions_data[modelseed_reaction_id] = modelseed_reaction_data
            if unadded_ec_numbers:
                # Each row of the table represents a unique EC number -> ModelSEED reaction mapping.
                modelseed_ec_reactions_dict: Dict[str, Dict] = modelseed_ec_reactions_table[
                    modelseed_ec_reactions_table['EC_number'].isin(unadded_ec_numbers)
                ].to_dict(orient='index')
                for modelseed_reaction_data in modelseed_ec_reactions_dict.values():
                    modelseed_reaction_id = modelseed_reaction_data['id']
                    if modelseed_reaction_id in modelseed_reactions_data:
                        # Data on the ModelSEED reaction has already been added to the list using a
                        # different EC number or KEGG REACTION ID.
                        continue
                    modelseed_reactions_data[modelseed_reaction_id] = modelseed_reaction_data
            if not modelseed_reactions_data:
                # The unadded KEGG REACTION IDs and EC numbers do not map to ModelSEED reactions and are not in the table.
                continue

            # Generate new reaction objects in the network.
            for modelseed_reaction_id, modelseed_reaction_data in modelseed_reactions_data.items():
                # Get the reaction object without having also created associated metabolite objects.
                reaction, modelseed_compound_ids = self._get_modelseed_reaction(modelseed_reaction_data)
                if reaction is None:
                    # For some reason, the reaction does not have a equation in the ModelSEED database.
                    continue
                ko.reactions[modelseed_reaction_id] = reaction
                # Record the KEGG REACTION IDs and EC numbers from the KO that yield the ModelSEED reaction.
                ko.kegg_reaction_aliases[modelseed_reaction_id] = aliased_kegg_reaction_ids = tuple(
                    set(unadded_kegg_reaction_ids).intersection(set(reaction.kegg_id_aliases))
                )
                ko.ec_number_aliases[modelseed_reaction_id] = aliased_ec_numbers = tuple(
                    set(unadded_ec_numbers).intersection(set(reaction.ec_number_aliases))
                )
                network.reactions[modelseed_reaction_id] = reaction
                for kegg_reaction_id in aliased_kegg_reaction_ids:
                    network.kegg_reactions[kegg_reaction_id].append(modelseed_reaction_id)
                for ec_number in aliased_ec_numbers:
                    network.ec_numbers[ec_number].append(modelseed_reaction_id)

                # Separate ModelSEED compound IDs that have previously been used to create
                # ModelSEEDCompound objects from those that have not.
                unadded_modelseed_compound_ids = []
                reaction_compounds = []
                for modelseed_compound_id in modelseed_compound_ids:
                    if modelseed_compound_id in network.metabolites:
                        # The ModelSEED compound ID has been encountered in previously processed reactions.
                        reaction_compounds.append(network.metabolites[modelseed_compound_id])
                    else:
                        unadded_modelseed_compound_ids.append(modelseed_compound_id)

                # Generate new metabolite objects in the network
                for modelseed_compound_id in unadded_modelseed_compound_ids:
                    try:
                        modelseed_compound_series: pd.Series = modelseed_compounds_table.loc[modelseed_compound_id]
                    except KeyError:
                        raise ConfigError(
                            f"A row for the ModelSEED compound ID, '{modelseed_compound_id}', was expected "
                            "but not found in the ModelSEED compounds table. This ID was found in the equation "
                            f"for ModelSEED reaction, '{modelseed_reaction_id}'."
                        )
                    modelseed_compound_data = modelseed_compound_series.to_dict()
                    modelseed_compound_data['id'] = modelseed_compound_id
                    compound = self._get_modelseed_compound(modelseed_compound_data)
                    reaction_compounds.append(compound)
                    network.metabolites[modelseed_compound_id] = compound
                reaction.compounds = tuple(reaction_compounds)

        if undefined_ko_ids:
            self.run.info_single(
                "Certain genes matched KOs that were not found in the KO database. "
                "It could be that the KOfams used to annotate genes were not from the same KEGG "
                "database version as the KO definition files. Here are the unrecognized KO IDs "
                f"matching genes in the contigs database: {', '.join(undefined_ko_ids)}"
            )
        self.progress.end()

        if store:
            if contigs_super.a_meta['reaction_network_ko_annotations_hash']:
                self.run.warning("Deleting existing reaction network from contigs database")
                cdb = ContigsDatabase(contigs_db)
                cdb.db._exec(f'''DELETE from {tables.gene_function_reactions_table_name}''')
                cdb.db._exec(f'''DELETE from {tables.gene_function_metabolites_table_name}''')
                cdb.disconnect()
                self.run.info_single("Deleted data in gene function reactions and metabolites tables", nl_after=1)

            self.progress.new("Saving reaction network to contigs database")
            self.progress.update("Reactions table")
            self._store_contigs_database_reactions(network, contigs_db)
            self.progress.update("Metabolites table")
            self._store_contigs_database_metabolites(network, contigs_db)

            self.progress.update("Metadata")
            ko_annotations_hash = self.hash_ko_annotations(gene_function_calls_dict)
            cdb = ContigsDatabase(contigs_db)
            cdb.db.set_meta_value('reaction_network_ko_annotations_hash', ko_annotations_hash)
            cdb.db.set_meta_value('reaction_network_kegg_database_release', self.kegg_db.release)
            cdb.db.set_meta_value('reaction_network_modelseed_database_sha', self.modelseed_db.sha)
            cdb.disconnect()
            self.progress.end()

        stats = {}
        self.run.info_single("METABOLIC REACTION NETWORK STATISTICS", mc='green', nl_after=1)

        self.progress.new("Counting genes and KOs")
        self.progress.update("...")

        # Count all gene calls in the genome.
        cdb = ContigsDatabase(contigs_db)
        stats['Total gene calls in genome'] = gene_call_count = cdb.db.get_row_counts_from_table('genes_in_contigs')
        cdb.disconnect()
        stats['Genes annotated with KOs'] = ko_annotated_gene_count = len(network.genes)

        # Count genes contributing to the reaction network.
        contributing_gene_count = 0
        for gene in network.genes.values():
            for ko in gene.kos:
                if ko.reactions:
                    contributing_gene_count += 1
                    break
        stats['Genes contributing to network'] = contributing_gene_count

        stats['KOs annotating genes'] = annotating_ko_count = len(network.kos)
        # Count KOs contributing to the reaction network.
        contributing_ko_count = 0
        for ko in network.kos.values():
            if ko.reactions:
                contributing_ko_count += 1
        stats['KOs contributing to network'] = contributing_ko_count
        self.progress.end()

        self.run.info_single("Gene calls and KEGG Ortholog (KO) annotations")
        self.run.info("Total gene calls in genome", gene_call_count)
        self.run.info("Genes annotated with KOs", ko_annotated_gene_count)
        self.run.info("Genes contributing to network", contributing_gene_count)
        self.run.info("KOs annotating genes", annotating_ko_count)
        self.run.info("KOs contributing to network", contributing_ko_count, nl_after=1)

        self.progress.new("Counting reactions and KO sources")
        self.progress.update("...")

        stats['Reactions (ModelSEED) in network'] = reaction_count = len(network.reactions)
        contributing_reaction_counts = []
        for ko in network.kos.values():
            if ko.reactions:
                contributing_reaction_counts.append(len(ko.reactions))
        stats['Max rxns per KO'] = max_reactions_per_ko = max(contributing_reaction_counts)
        stats['Mean rxns per contributing KO'] = mean_reactions_per_contributing_ko = round(np.mean(contributing_reaction_counts), 1)
        stats['Stdev rxns per contributing KO'] = std_reactions_per_contributing_ko = round(np.std(contributing_reaction_counts), 1)
        self.progress.end()

        self.run.info_single("Reactions and KO sources")
        self.run.info("Rxns (ModelSEED) in network", reaction_count)
        self.run.info("Max rxns per KO", max_reactions_per_ko)
        self.run.info("Mean rxns per KO", mean_reactions_per_contributing_ko)
        self.run.info("Stdev rxns per KO", std_reactions_per_contributing_ko, nl_after=1)

        self.progress.new("Counting reactions from each alias source")
        self.progress.update("...")

        kegg_reaction_source_count = 0
        ec_number_source_count = 0
        both_source_count = 0
        for reaction in network.reactions.values():
            if reaction.kegg_id_aliases:
                kegg_reaction_source_count += 1
            if reaction.ec_number_aliases:
                ec_number_source_count += 1
            if reaction.kegg_id_aliases and reaction.ec_number_aliases:
                both_source_count += 1
        only_kegg_reaction_source_count = kegg_reaction_source_count - both_source_count
        only_ec_number_source_count = ec_number_source_count - both_source_count
        self.progress.end()

        self.run.info_single("Reaction alias source comparison")
        self.run.info("Rxns aliased by KEGG rxn", kegg_reaction_source_count)
        self.run.info("Rxns aliased by EC number", ec_number_source_count)
        self.run.info("Rxns aliased by KEGG rxn & EC number", both_source_count)
        self.run.info("Rxns aliased only by KEGG rxn", only_kegg_reaction_source_count)
        self.run.info("Rxns aliased only by EC number", only_ec_number_source_count, nl_after=1)

        self.progress.new("Counting KEGG REACTION sources")
        self.progress.update("...")

        modelseed_alias_counts = []
        contributing_modelseed_alias_counts = []
        for kegg_reaction_id, modelseed_reaction_ids in network.kegg_reactions.items():
            modelseed_alias_counts.append(len(modelseed_reaction_ids))
            if modelseed_reaction_ids:
                contributing_modelseed_alias_counts.append(len(modelseed_reaction_ids))
        stats['Mean rxns sourced per KO KEGG rxn'] = mean_reactions_per_kegg_id = round(np.mean(modelseed_alias_counts), 1)
        stats['Stdev rxns sourced per KO KEGG rxn'] = std_reactions_per_kegg_id = round(np.std(modelseed_alias_counts), 1)
        stats['Max rxns sourced per KO KEGG rxn'] = max_reactions_per_kegg_id = max(modelseed_alias_counts)
        stats['KEGG rxns contributing to network'] = contributing_kegg_reaction_count = len(contributing_modelseed_alias_counts)
        stats['Noncontributing KO KEGG rxns'] = noncontributing_kegg_reaction_count = len(network.kegg_reactions) - len(contributing_modelseed_alias_counts)
        stats['Mean rxns sourced per contributing KEGG rxn'] = mean_reactions_per_contributing_kegg_id = round(np.mean(contributing_modelseed_alias_counts), 1)
        stats['Stdev rxns sourced per contributing KEGG rxn'] = std_reactions_per_contributing_kegg_id = round(np.std(contributing_modelseed_alias_counts), 1)
        self.progress.end()

        self.run.info_single("KO KEGG REACTION sources")
        self.run.info("Mean rxns sourced per KO KEGG rxn", mean_reactions_per_kegg_id)
        self.run.info("Stdev rxns sourced per KO KEGG rxn", std_reactions_per_kegg_id)
        self.run.info("Max rxns sourced per KO KEGG rxn", max_reactions_per_kegg_id)
        self.run.info("KEGG rxns contributing to network", contributing_kegg_reaction_count)
        self.run.info("Noncontributing KO KEGG rxns", noncontributing_kegg_reaction_count)
        self.run.info("Mean rxns sourced per contributing KEGG rxn", mean_reactions_per_contributing_kegg_id)
        self.run.info("Stdev rxns sourced per contributing KEGG rxn", std_reactions_per_contributing_kegg_id, nl_after=1)

        self.progress.new("Counting EC number reaction sources")
        self.progress.update("...")

        modelseed_alias_counts = []
        contributing_modelseed_alias_counts = []
        for ec_number, modelseed_reaction_ids in network.ec_numbers.items():
            modelseed_alias_counts.append(len(modelseed_reaction_ids))
            if modelseed_reaction_ids:
                contributing_modelseed_alias_counts.append(len(modelseed_reaction_ids))
        stats['Mean rxns sourced per KO EC number'] = mean_reactions_per_ec_number = round(np.mean(modelseed_alias_counts), 1)
        stats['Stdev rxns sourced per KO EC number'] = std_reactions_per_ec_number = round(np.std(modelseed_alias_counts), 1)
        stats['Max rxns sourced per KO EC number'] = max_reactions_per_ec_number = max(modelseed_alias_counts)
        stats['EC numbers contributing to network'] = contributing_ec_number_count = len(contributing_modelseed_alias_counts)
        stats['Noncontributing EC numbers'] = noncontributing_ec_number_count = len(network.ec_numbers) - len(contributing_modelseed_alias_counts)
        stats['Mean rxns sourced per contributing EC number'] = mean_reactions_per_contributing_ec_number = round(np.mean(contributing_modelseed_alias_counts), 1)
        stats['Stdev rxns sourced per contributing EC number'] = std_reactions_per_contributing_ec_number = round(np.std(contributing_modelseed_alias_counts), 1)
        self.progress.end()

        self.run.info_single("KO EC number reaction sources")
        self.run.info("Mean rxns sourced per KO EC number", mean_reactions_per_ec_number)
        self.run.info("Stdev rxns sourced per KO EC number", std_reactions_per_ec_number)
        self.run.info("Max rxns sourced per KO EC number", max_reactions_per_ec_number)
        self.run.info("EC numbers contributing to network", contributing_ec_number_count)
        self.run.info("Noncontributing KO EC numbers", noncontributing_ec_number_count)
        self.run.info("Mean rxns sourced per contributing EC number", mean_reactions_per_contributing_ec_number)
        self.run.info("Stdev rxns sourced per contributing EC number", std_reactions_per_contributing_ec_number, nl_after=1)

        self.progress.new("Counting reactions and metabolites by property")
        self.progress.update("...")

        reversible_count = 0
        irreversible_count = 0
        cytoplasmic_compound_ids = []
        extracellular_compound_ids = []
        consumed_compound_ids = []
        produced_compound_ids = []
        compound_reaction_counts = {}
        for reaction in network.reactions.values():
            if reaction.reversibility:
                reversible_count += 1
            else:
                irreversible_count += 1
            encountered_compound_ids = []
            for compartment, coefficient, compound in zip(reaction.compartments, reaction.coefficients, reaction.compounds):
                compound_id = compound.modelseed_id
                if compartment == 'c':
                    cytoplasmic_compound_ids.append(compound_id)
                else:
                    extracellular_compound_ids.append(compound_id)
                if reaction.reversibility:
                    consumed_compound_ids.append(compound_id)
                    produced_compound_ids.append(compound_id)
                elif coefficient < 0:
                    consumed_compound_ids.append(compound_id)
                else:
                    produced_compound_ids.append(compound_id)
                if compound_id not in encountered_compound_ids:
                    try:
                        compound_reaction_counts[compound_id] += 1
                    except KeyError:
                        compound_reaction_counts[compound_id] = 1
        stats['Reversible rxns'] = reversible_count
        stats['Irreversible rxns'] = irreversible_count
        cytoplasmic_compound_ids = set(cytoplasmic_compound_ids)
        extracellular_compound_ids = set(extracellular_compound_ids)
        stats['Metabolites in network'] = metabolite_count = len(network.metabolites)
        stats['Cytoplasmic metabolites'] = cytoplasmic_count = len(cytoplasmic_compound_ids)
        stats['Extracellular metabolites'] = extracellular_count = len(extracellular_compound_ids)
        stats['Exclusively cytoplasmic metabolites'] = exclusively_cytoplasmic_count = len(cytoplasmic_compound_ids.difference(extracellular_compound_ids))
        stats['Exclusively extracellular metabolites'] = exclusively_extracellular_count = len(extracellular_compound_ids.difference(cytoplasmic_compound_ids))
        stats['Cytoplasmic/extracellular metabolites'] = cytoplasmic_plus_extracellular_count = len(cytoplasmic_compound_ids.intersection(extracellular_compound_ids))
        consumed_compound_ids = set(consumed_compound_ids)
        produced_compound_ids = set(produced_compound_ids)
        stats['Consumed metabolites'] = consumed_count = len(consumed_compound_ids)
        stats['Produced metabolites'] = produced_count = len(produced_compound_ids)
        stats['Exclusively consumed metabolites'] = exclusively_consumed_count = len(consumed_compound_ids.difference(produced_compound_ids))
        stats['Exclusively produced metabolites'] = exclusively_produced_count = len(produced_compound_ids.difference(consumed_compound_ids))
        stats['Consumed/produced metabolites'] = consumed_plus_produced_count = len(consumed_compound_ids.intersection(produced_compound_ids))
        metabolite_reaction_counts = collections.Counter(compound_reaction_counts.values())
        stats['Metabolites consumed or produced by 1 rxns'] = one_reaction_count = metabolite_reaction_counts[1]
        stats['Metabolites consumed or produced by 2 rxns'] = two_reactions_count = metabolite_reaction_counts[2]
        stats['Metabolites consumed or produced by 3+ rxns'] = three_plus_reactions_count = metabolite_count - one_reaction_count - two_reactions_count
        self.progress.end()

        self.run.info_single("Reaction reversibility")
        self.run.info("Reversible rxns", reversible_count)
        self.run.info("Irreversible rxns", irreversible_count, nl_after=1)

        self.run.info_single("Metabolites and localization")
        self.run.info("Metabolites in network", metabolite_count)
        self.run.info("Cytoplasmic metabolites", cytoplasmic_count)
        self.run.info("Extracellular metabolites", extracellular_count)
        self.run.info("Exclusively cytoplasmic metabolites", exclusively_cytoplasmic_count)
        self.run.info("Exclusively extracellular metabolites", exclusively_extracellular_count)
        self.run.info("Cytoplasmic/extracellular metabolites", cytoplasmic_plus_extracellular_count, nl_after=1)

        self.run.info_single("Metabolite consumption and production")
        self.run.info("Consumed metabolites", consumed_count)
        self.run.info("Produced metabolites", produced_count)
        self.run.info("Exclusively consumed metabolites", exclusively_consumed_count)
        self.run.info("Exclusively produced metabolites", exclusively_produced_count)
        self.run.info("Consumed/produced metabolites", consumed_plus_produced_count)
        self.run.info("Metabolites consumed or produced by 1 rxn", one_reaction_count)
        self.run.info("Metabolites consumed or produced by 2 rxns", two_reactions_count)
        self.run.info("Metabolites consumed or produced by 3+ rxns", three_plus_reactions_count)

        return network

    def _get_modelseed_reaction(self, modelseed_reaction_data: Dict) -> Tuple[ModelSEEDReaction, List[str]]:
        """
        Generate a ModelSEED reaction object and list of associated ModelSEED compound IDs from the
        ModelSEED reaction table entry. The reaction object is not populated with metabolite objects
        from the list of associated compound IDs.

        Parameters
        ==========
        modelseed_reaction_data : Dict
            A dictionary representation of a row for a reaction in the ModelSEED reaction table set
            up by anvi'o.

        Returns
        =======
        ModelSEEDReaction
            An object representation of the ModelSEED reaction.

        List[str]
            ModelSEED compound IDs of reaction reactants and products.
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
            compartments.append(ModelSEEDDatabase.compartment_ids[int(split_entry[2])])
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

    def _to_lcm_denominator(self, floats: List[float]) -> Tuple[int]:
        """
        Convert a list of numbers to their lowest common integer multiples.

        Parameters
        ==========
        floats : List[float]

        Returns
        =======
        List[int]
        """
        def lcm(a, b):
            return a * b // math.gcd(a, b)
        rationals = [fractions.Fraction(f).limit_denominator() for f in floats]
        lcm_denom = functools.reduce(lcm, [r.denominator for r in rationals])
        return list(int(r.numerator * lcm_denom / r.denominator) for r in rationals)

    def _get_modelseed_compound(self, modelseed_compound_data: Dict) -> ModelSEEDCompound:
        """
        Generate a ModelSEED compound object from its entry in the ModelSEED table.

        Parameters
        ==========
        modelseed_compound_data : Dict
            A dictionary representation of a row for a compound in the ModelSEED compound table set
            up by anvi'o.

        Returns
        =======
        ModelSEEDCompound
            An object representation of the ModelSEED compound.
        """
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

    def _store_contigs_database_reactions(self, network: GenomicNetwork, contigs_db: str) -> None:
        """
        Store reaction data in the relevant contigs database table.

        Parameters
        ==========
        network : GenomicNetwork
            The reaction network generated from gene KO annotations in the contigs database.

        contigs_db : str
            The path to the contigs database from which the reaction network was generated.
        """
        # Transfer data from reaction objects to dictionaries mapping to table entries.
        reactions_data: Dict[str, Dict] = {}
        for modelseed_reaction_id, reaction in network.reactions.items():
            reaction_data = {}
            reaction_data['modelseed_reaction_id'] = modelseed_reaction_id
            reaction_data['modelseed_reaction_name'] = reaction.modelseed_name
            reaction_data['metabolite_modelseed_ids'] = ', '.join([c.modelseed_id for c in reaction.compounds])
            reaction_data['stoichiometry'] = ', '.join([str(c) for c in reaction.coefficients])
            reaction_data['compartments'] = ', '.join(reaction.compartments)
            reaction_data['reversibility'] = reaction.reversibility
            reactions_data[modelseed_reaction_id] = reaction_data

        # Get *KO* KEGG REACTION ID and EC number aliases of each ModelSEED reaction. These are not
        # all possible aliases, but only those associated with KOs that matched genes. Structure
        # alias data as follows:
        # <ModelSEED reaction ID>: {
        #   <KEGG REACTION ID 1>: [<KO IDs associated with KEGG REACTION ID 1>],
        #   <KEGG REACTION ID 2>: [<KO IDs associated with KEGG REACTION ID 2>],
        #   ...
        # }
        # <ModelSEED reaction ID>: {
        #   <EC number 1>: [<KO IDs associated with EC number 1>],
        #   <EC number 2>: [<KO IDs associated with EC number 2>],
        # ...
        # }
        ko_reaction_aliases: Dict[str, Tuple[Dict[str, List[str]], Dict[str, List[str]]]] = {
            modelseed_id: ({}, {}) for modelseed_id in reactions_data
        }
        for ko_id, ko in network.kos.items():
            for modelseed_id, reaction in ko.reactions.items():
                aliases = ko_reaction_aliases[modelseed_id]

                kegg_reaction_aliases = aliases[0]
                kegg_reaction_ids = ko.kegg_reaction_aliases[modelseed_id]
                for kegg_reaction_id in kegg_reaction_ids:
                    try:
                        ko_ids: List = kegg_reaction_aliases[kegg_reaction_id]
                    except KeyError:
                        kegg_reaction_aliases[kegg_reaction_id] = ko_ids = []
                    ko_ids.append(ko_id)

                ec_number_aliases = aliases[1]
                ec_numbers = ko.ec_number_aliases[modelseed_id]
                for ec_number in ec_numbers:
                    try:
                        ko_ids: List = ec_number_aliases[ec_number]
                    except KeyError:
                        ec_number_aliases[ec_number] = ko_ids = []
                    ko_ids.append(ko_id)
        for modelseed_id, aliases in ko_reaction_aliases.items():
            reaction_data = reactions_data[modelseed_id]

            # Make the entry for KO KEGG REACTION aliases, which looks akin to the following arbitrary example:
            # 'R00001: (K00010, K00100); R01234: (K54321)'
            kegg_reaction_aliases = aliases[0]
            entry = []
            for kegg_reaction_id, ko_ids in kegg_reaction_aliases.items():
                entry.append(f'{kegg_reaction_id}: ({", ".join(sorted(ko_ids))})')
            reaction_data['ko_kegg_reaction_source'] = '; '.join(sorted(entry))

            # Make the entry for KO EC number aliases, which looks akin to the following arbitrary example:
            # '1.1.1.1: (K00010, K00100); 1.2.3.4: (K12345); 6.7.8.99: (K65432)
            ec_number_aliases = aliases[1]
            entry = []
            for ec_number, ko_ids in ec_number_aliases.items():
                entry.append(f'{ec_number}: ({", ".join(sorted(ko_ids))})')
            reaction_data['ko_ec_number_source'] = '; '.join(sorted(entry))

        reactions_table = pd.DataFrame.from_dict(reactions_data, orient='index').reset_index(drop=True).sort_values('modelseed_reaction_id')
        reactions_table = reactions_table[tables.gene_function_reactions_table_structure]

        cdb = ContigsDatabase(contigs_db)
        cdb.db._exec_many(
            f'''INSERT INTO {tables.gene_function_reactions_table_name} VALUES ({','.join('?' * len(tables.gene_function_reactions_table_structure))})''',
            reactions_table.values
        )
        cdb.disconnect()

    def _store_contigs_database_metabolites(self, network: GenomicNetwork, contigs_db: str) -> None:
        """
        Store metabolite data in the relevant contigs database table.

        Parameters
        ==========
        network : GenomicNetwork
            The reaction network generated from gene KO annotations in the contigs database.

        contigs_db : str
            The path to the contigs database from which the reaction network was generated.

        Returns
        =======
        None
        """
        # Transfer data from metabolite objects to dictionaries mapping to table entries.
        metabolites_data = {}
        for modelseed_compound_id, compound in network.metabolites.items():
            metabolite_data = {}
            metabolite_data['modelseed_compound_id'] = modelseed_compound_id
            metabolite_data['modelseed_compound_name'] = compound.modelseed_name
            metabolite_data['formula'] = compound.formula
            metabolite_data['charge'] = compound.charge
            metabolites_data[modelseed_compound_id] = metabolite_data

        metabolites_table = pd.DataFrame.from_dict(metabolites_data, orient='index').reset_index(drop=True).sort_values('modelseed_compound_id')
        metabolites_table = metabolites_table[tables.gene_function_metabolites_table_structure]

        cdb = ContigsDatabase(contigs_db)
        cdb.db._exec_many(
            f'''INSERT INTO {tables.gene_function_metabolites_table_name} VALUES ({','.join('?' * len(tables.gene_function_metabolites_table_structure))})''',
            metabolites_table.values
        )
        cdb.disconnect()

    def hash_ko_annotations(self, gene_function_calls_dict: Dict) -> str:
        """
        Hash gene KO annotations in a contigs database to concisely represent the data used to construct a reaction network.

        Parameters
        ==========
        gene_function_calls_dict : str
            Dictionary containing gene KO annotations loaded by a contigs superclass.

        Returns
        =======
        str
            Hash representation of all gene KO annotations.
        """
        ko_annotations = []
        for gcid, gene_dict in gene_function_calls_dict.items():
            ko_data = gene_dict['KOfam']
            ko_id = ko_data[0]
            ko_name = ko_data[1]
            e_value = ko_data[2]
            ko_annotations.append((str(gcid), ko_id, ko_name, str(e_value)))
        # Sort KO annotation data in ascending order of gene caller ID and KO accession.
        ko_annotations = sorted(ko_annotations, key=lambda x: (x[0], x[1]))

        ko_annotations_string = ''
        for ko_annotation in ko_annotations:
            ko_annotations_string += ''.join(ko_annotation)

        hashed_ko_annotations = hashlib.sha1(ko_annotations_string.encode('utf-8')).hexdigest()
        return hashed_ko_annotations

    def make_pangenomic_network(
        self,
        genomes_storage_db: str,
        pan_db: str,
        store: bool = True,
        overwrite_existing_network: bool = False
    ) -> PangenomicNetwork:
        """
        Make a pangenomic metabolic reaction network from KEGG Orthologs stored a genomes storage
        database and gene clusters stored in a pan database.

        Parameters
        ==========
        genomes_storage_db : str
            Path to a genomes storage database. The pangenomic network is derived from gene KO
            annotations stored in the database.

        pan_db : str
            Path to a pan database. The pangenomic network is determined for gene clusters stored in
            the database.

        Returns
        =======
        PangenomicNetwork
            The network derived from the pangenomic databases.
        """
        return
