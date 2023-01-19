#!/usr/bin/env python
# -*- coding: utf-8
"""This file contains CAZyme related classes."""

import os
import glob
import shutil

import anvio
import anvio.dbops as dbops
import anvio.utils as utils
import anvio.terminal as terminal
import anvio.filesnpaths as filesnpaths

from anvio.errors import ConfigError
from anvio.drivers.hmmer import HMMer
from anvio.parsers import parser_modules
from anvio.tables.genefunctions import TableForGeneFunctions

__author__ = "Developers of anvi'o (see AUTHORS.txt)"
__copyright__ = "Copyleft 2015-2020, the Meren Lab (http://merenlab.org/)"
__license__ = "GPL 3.0"
__version__ = anvio.__version__
__maintainer__ = "Matthew Schechter"
__email__ = "mschechter@uchicago.edu"

run = terminal.Run()
progress = terminal.Progress()
pp = terminal.pretty_print

class CAZymeSetup(object):
    def __init__(self, args, run=run, progress=progress):
        """Setup a CAZyme database for anvi'o

        http://www.cazy.org/

        Parameters
        ==========
        args : argparse.Namespace
            See `bin/anvi-setup-cazymes` for available arguments
            - cazyme_data_dir : str, optional
                The directory where the CAZyme data should be stored. If not provided, the data will be stored in the anvi'o data directory.
            - reset : bool, optional
                If True, the data directory will be deleted and recreated. Defaults to False.
        run : terminal.Run, optional
            An object for printing messages to the console.
        progress : terminal.Progress, optional
            An object for printing progress bars to the console.
        """

        self.args = args
        self.run = run
        self.progress = progress
        self.cazyme_data_dir = args.cazyme_data_dir

        filesnpaths.is_program_exists('hmmpress')
        
        if self.cazyme_data_dir and args.reset:
            raise ConfigError("You are attempting to run CAZyme setup on a non-default data directory (%s) using the --reset flag. "
                              "To avoid automatically deleting a directory that may be important to you, anvi'o refuses to reset "
                              "directories that have been specified with --cazyme-data-dir. If you really want to get rid of this "
                              "directory and regenerate it with CAZyme data inside, then please remove the directory yourself using "
                              "a command like `rm -r %s`. We are sorry to make you go through this extra trouble, but it really is "
                              "the safest way to handle things." % (self.cazyme_data_dir, self.cazyme_data_dir))

        if not self.cazyme_data_dir:
            self.cazyme_data_dir = os.path.join(os.path.dirname(anvio.__file__), 'data/misc/CAZyme')

        filesnpaths.is_output_dir_writable(os.path.dirname(os.path.abspath(self.cazyme_data_dir)))

        self.resolve_database_url()

        if not args.reset and not anvio.DEBUG:
            self.is_database_exists()

        if args.reset:
            filesnpaths.gen_output_directory(self.cazyme_data_dir, delete_if_exists=True, dont_warn=True)
        else:
            filesnpaths.gen_output_directory(self.cazyme_data_dir)

    def resolve_database_url(self):
        """Create path to CAZyme ftp

        Added self values
        ================= 
        - self.page_index : string
            version of CAZyme database

        """
        if self.args.cazyme_version:
            self.page_index = self.args.cazyme_version 
            self.run.info('Attempting to use version', self.args.cazyme_version)
        else:
            self.page_index = 'V11'
            self.run.info_single('No CAZyme version specified. Using current release.')

        self.database_url = os.path.join("https://bcb.unl.edu/dbCAN2/download/Databases", f"{self.page_index}", f"dbCAN-HMMdb-{self.page_index}.txt") 

    def is_database_exists(self):
        """Determine if CAZyme database has already been downloaded"""
        if os.path.exists(os.path.join(self.cazyme_data_dir, f"dbCAN-HMMdb-{self.page_index}.txt")):
            raise ConfigError(f"It seems you already have CAZyme database installed in {self.cazyme_data_dir}, please use --reset flag if you want to re-download it.")

    def download(self, hmmpress_files=True):
        """Download CAZyme database and compress with hmmpress"""
        self.run.info("Database URL", self.database_url)

        utils.download_file(self.database_url, os.path.join(self.cazyme_data_dir, os.path.basename(self.database_url)) , progress=self.progress, run=self.run)

        if hmmpress_files:
            self.hmmpress_files()

    def hmmpress_files(self):
        """Runs hmmpress on CAZyme HMM profiles."""

        file_path = os.path.join(self.cazyme_data_dir, os.path.basename(self.database_url))
        cmd_line = ['hmmpress', file_path]
        log_file_path = os.path.join(self.cazyme_data_dir, '00_hmmpress_log.txt')
        ret_val = utils.run_command(cmd_line, log_file_path)

        if ret_val:
            raise ConfigError("Hmm. There was an error while running `hmmpress` on the Pfam HMM profiles. "
                                "Check out the log file ('%s') to see what went wrong." % (log_file_path))
        else:
            # getting rid of the log file because hmmpress was successful
            os.remove(log_file_path)

class CAZyme(object):
    """Search CAZyme database over contigs-db

    Parameters
    ==========
    args : argparse.Namespace
        See `bin/anvi-run-cazymes` for available arguments
        - noise_cutoff_terms : str, optional
            Filtering option for HMM search
        - hmm_program : str, optional
            hmmsearch (default) or hmmscan
    run : terminal.Run, optional
        An object for printing messages to the console.
    progress : terminal.Progress, optional
        An object for printing progress bars to the console.
    """
    def __init__(self, args, run=run, progress=progress):

        self.run = run
        self.progress = progress

        A = lambda x, t: t(args.__dict__[x]) if x in args.__dict__ else None
        null = lambda x: x
        self.contigs_db_path = A('contigs_db', null)
        self.num_threads = A('num_threads', null)
        self.hmm_program = A('hmmer_program', null) or 'hmmsearch'
        self.noise_cutoff_terms = A('noise_cutoff_terms', null)

        # load_catalog will populate this
        self.function_catalog = {}

        filesnpaths.is_program_exists(self.hmm_program)
        utils.is_contigs_db(self.contigs_db_path)

        self.cazyme_data_dir = os.path.join(os.path.dirname(anvio.__file__), 'data/misc/CAZyme')

        self.is_database_exists()

    def is_database_exists(self):
        """Checks if decompressed database files exist"""

        if not glob.glob(os.path.join(self.cazyme_data_dir, "dbCAN-HMMdb-*.txt")):
            raise ConfigError(f"It seems you do not have the CAZyme database installed in {self.cazyme_data_dir}, "
                              f"please run 'anvi-setup-cazymes' download it.")

        # Glob and find what files we have then check if we have them all
        downloaded_files = glob.glob(os.path.join(self.cazyme_data_dir, '*'))
        
        # here we check if the HMM profile is compressed so we can decompress it for next time
        hmmpress_file_extensions = ["h3f", "h3i", "h3m", "h3p", "txt"]
        extant_extensions = [os.path.basename(file).split(".")[-1] for file in downloaded_files]

        if hmmpress_file_extensions.sort() != extant_extensions.sort():
            raise ConfigError("Anvi'o detected that the CAZyme database was not properly compressed with hmmpress. "
                              "Please 'anvi-setup-cazymes --reset'")

    def process(self):
        """Search CAZyme HMMs over contigs-db, parse, and filter results"""

        #FIXME: need a smarter way to find the CAZyme HMM file for when users 
        # want a specific version. This will break if it's not V11
        hmm_file = os.path.join(self.cazyme_data_dir, "dbCAN-HMMdb-V11.txt")

        # initialize contigs database
        class Args: pass
        args = Args()
        args.contigs_db = self.contigs_db_path
        contigs_db = dbops.ContigsSuperclass(args)
        tmp_directory_path = filesnpaths.get_temp_directory_path()

        # get an instance of gene functions table
        gene_function_calls_table = TableForGeneFunctions(self.contigs_db_path, self.run, self.progress)

        # export AA sequences for genes
        target_files_dict = {'AA:GENE': os.path.join(tmp_directory_path, 'AA_gene_sequences.fa')}
        contigs_db.get_sequences_for_gene_callers_ids(output_file_path=target_files_dict['AA:GENE'],
                                                      simple_headers=True,
                                                      report_aa_sequences=True)

        # run hmmer
        hmmer = HMMer(target_files_dict, num_threads_to_use=self.num_threads, program_to_use=self.hmm_program)
        hmm_hits_file = hmmer.run_hmmer('CAZymes', 'AA', 'GENE', None, None, len(self.function_catalog), hmm_file, None, self.noise_cutoff_terms)

        if not hmm_hits_file:
            run.info_single("The HMM search returned no hits :/ So there is nothing to add to the contigs database. But "
                            "now anvi'o will add CAZymes as a functional source with no hits, clean the temporary directories "
                            "and gracefully quit.", nl_before=1, nl_after=1)
            shutil.rmtree(tmp_directory_path)
            hmmer.clean_tmp_dirs()
            gene_function_calls_table.add_empty_sources_to_functional_sources({'Pfam'})
            return

        # parse hmmer output
        parser = parser_modules['search']['hmmer_table_output'](hmm_hits_file, alphabet='AA', context='GENE', program=self.hmm_program)
        search_results_dict = parser.get_search_results()

        # add functions to database
        functions_dict = {}
        counter = 0
        for hmm_hit in search_results_dict.values():
            functions_dict[counter] = {
                'gene_callers_id': hmm_hit['gene_callers_id'],
                'source': 'CAZyme',
                'accession': hmm_hit['gene_hmm_id'],
                'function': hmm_hit['gene_name'],
                'e_value': hmm_hit['e_value']
            }

            counter += 1

        if functions_dict:
            gene_function_calls_table.create(functions_dict)
        else:
            self.run.warning("CAZyme class has no hits to process. Returning empty handed, but still adding CAZyme as "
                             "a functional source.")
            gene_function_calls_table.add_empty_sources_to_functional_sources({'CAZyme'})

        if anvio.DEBUG:
            run.warning("The temp directories, '%s' and '%s' are kept. Please don't forget to clean those up "
                        "later" % (tmp_directory_path, ', '.join(hmmer.tmp_dirs)), header="Debug")
        else:
            run.info_single('Cleaning up the temp directory (you can use `--debug` if you would '
                            'like to keep it for testing purposes)', nl_before=1, nl_after=1)
            shutil.rmtree(tmp_directory_path)
            hmmer.clean_tmp_dirs()