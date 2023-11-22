#!/usr/bin/env python
# -*- coding: utf-8
"""This file contains classes related to metabolism estimation, especially for user-defined metabolic pathways."""

import anvio
import anvio.terminal as terminal
import anvio.filesnpaths as filesnpaths
import anvio.utils as utils

from anvio.errors import ConfigError

__author__ = "Developers of anvi'o (see AUTHORS.txt)"
__copyright__ = "Copyleft 2015-2023, the Meren Lab (http://merenlab.org/)"
__license__ = "GPL 3.0"
__version__ = anvio.__version__
__maintainer__ = "Iva Veseli"
__email__ = "iva.veseli@hifmb.de"

run = terminal.Run()
progress = terminal.Progress()
run_quiet = terminal.Run(log_file_path=None, verbose=False)
progress_quiet = terminal.Progress(verbose=False)
P = terminal.pluralize

## REQUIRED FIELDS FOR A PATHWAY FILE
## AND THEIR ACCEPTABLE VALUES (IF APPLICABLE)
REQ_FIELDS = {'type': {'accepted_vals': ['pathway', 'enzyme set'], 'data_type': str},
              'source': {'accepted_vals': ['KEGG', 'user'], 'data_type': str},
              'functional_definition': {'data_type': list},
              'functions': {'data_type': dict},
            }

class PathwayYAML:
    """A class to store definitions of metabolic pathways from YAML-formatted data. 

    The data must be provided either in the form of a YAML file, or as a dictionary.
    
    PARAMETERS
    ==========
    file_path : str
        path to input YAML file
    path_dict : dict
        dictionary containing the pathway info, ie from an already-parsed YAML file
    """

    def __init__(self, file_path: str = None, path_dict: dict = None):

        if not file_path and not path_dict:
            raise ConfigError("The PathwayYAML class requires an input. You should provide either a path to a YAML file or a "
                              "dictionary of pathway information.")

        if file_path:
            self.file_path = file_path
            filesnpaths.is_file_exists(self.file_path)
            pathway_dict = utils.get_yaml_as_dict(self.file_path)
            if anvio.DEBUG:
                run.info_single(f"The pathway file {self.file_path} has been successfully loaded.")
        elif path_dict:
            self.file_path = None
            pathway_dict = path_dict
        
        num_pathways_in_file = len(pathway_dict.keys())
        if anvio.DEBUG:
            run.info("Number of pathways found", num_pathways_in_file)

        if num_pathways_in_file > 1:
            # check if user forgot to nest the pathway info within a dictionary keyed by pathway ID
            for key in pathway_dict.keys():
                if key in list(REQ_FIELDS.keys()):
                    raise ConfigError(f"We noticed that the top-level of the data dictionary contains pathway information, like '{key}'. "
                                      f"The first level of this dictionary should be the pathway ID (such as 'M00001'). Please nest the "
                                      f"pathway info one level lower in your input data.")
            raise ConfigError("We found more than one pathway in the input data, but we are not yet equipped to handle that :/ ")
        
        self.id = list(pathway_dict.keys())[0]
        self.dict = pathway_dict[self.id]

        self.parse_pathway_data()

        self.print_pathway()


    #### ACCESSOR FUNCTIONS ####
    def get_pathway_dict(self):
        """Returns the pathway dictionary."""

        return self.dict

    def print_pathway(self):
        """Prints the pathway to the terminal. Mainly for debugging output."""

        print(self.dict)


    #### PARSING AND SANITY CHECKING FUNCTIONS ####
    def check_required_fields(self):
        """Ensures that all required fields are defined in the pathway file."""

        for field, requirements in REQ_FIELDS.items():
            if field not in self.dict:
                raise ConfigError(f"The required field '{field}' was not found in the input data.")
            if 'accepted_vals' in requirements and (self.dict[field] not in requirements['accepted_vals']):
                raise ConfigError(f"There is an issue with the definition of {field} in the input pathway data. "
                                  f"This field has the value '{self.dict[field]}', but only the following values are accepted: "
                                  f"{', '.join(requirements['accepted_vals'])}")

            if not isinstance(self.dict[field], requirements['data_type']):
                raise ConfigError(f"There is an issue with the definition of {field} in the input pathway data. "
                                  f"This field is supposed to be of type '{requirements['data_type']}' but instead it is a {type(self.dict[field])}.")

    def parse_accessions_from_definition(self, passed_definition: str = None):
        """Returns a list of functional accessions from the definition string. 
        
        If no definition is passed using the `passed_definition` variable, this function works on the definition 
        stored in `self.definition_string`.

        PARAMETERS
        ==========
        passed_definition : str
            The definition string to parse (optional)
        """
        
        def_to_parse = self.definition_string
        if passed_definition:
            def_to_parse = passed_definition

        substrs_to_remove = ['(',')', 'and', 'or']
        for r in substrs_to_remove:
            def_to_parse = def_to_parse.replace(r, '')
        acc_list = def_to_parse.split()
        return acc_list
                
    def crosscheck_definition_and_functions(self):
        """Verifies that every accession in the functional definition has a corresponding entry in the functions dict."""

        acc_missing_from_functions_field = []
        for a in self.parse_accessions_from_definition():
            if a not in self.functions:
                acc_missing_from_functions_field.append(a)
        
        if acc_missing_from_functions_field:
            acc_str = ", ".join(acc_missing_from_functions_field)
            n = len(acc_missing_from_functions_field)
            raise ConfigError(f"There {P('is a function', n, alt='are some functions')} in the functional definition for pathway "
                              f"{self.id} that {P('is', n, alt='are')} missing from the 'functions' field in the input data. Please "
                              f"add an entry for each accession into the 'functions' field. Here {P('is the accession', n, alt='are the accessions')} "
                              f"that you should add before trying to parse the pathway data again: {acc_str}")

    def function_sanity_checks(self):
        """Checks the formatting of each individual function within the self.functions dictionary.
        
        Each function requires at least an annotation 'source'.
        """

        for accession, function_data in self.functions.items():
            if 'source' not in function_data or function_data['source'] is None:
                raise ConfigError(f"The function {accession} does not have an associated annotation source. Please add "
                                  f"one using the key 'source' to ensure that we will be able to find the annotations "
                                  f"corresponding to this function later. If you don't know the annotation source for "
                                  f"this function, this webpage might help: https://anvio.org/help/main/artifacts/user-modules-data/#1-find-the-enzymes")

    def parse_pathway_data(self):
        """Parses the pathway dictionary to obtain the attributes of the pathway. 
        
        This function also performs sanity checking on the data inside critical fields.
        """

        self.check_required_fields()

        # attributes from required fields
        self.source = self.dict['source']
        self.type = self.dict['type']
        self.functional_definition = self.dict['functional_definition']
        self.functions = self.dict['functions']

        # attributes from optional fields that may be important downstream
        self.name = self.dict['name'] if 'name' in self.dict else 'UNDEFINED'

        # create other useful forms of the input data
        self.definition_string = " and ".join(['('+step+')' for step in self.functional_definition])

        # sanity checks
        self.crosscheck_definition_and_functions()
        self.function_sanity_checks()


class KeggYAML(PathwayYAML):
    """A special version of the PathwayYAML class that can handle data in the KEGG format.

    This class reads data from KEGG module files and puts it into the YAML format so that it 
    can henceforth be accessed via the regular PathwayYAML class.

    PARAMETERS
    ==========
    file_path : str
        path to KEGG module file
    run, progress : instances of terminal.Run() and terminal.Progress(), respectively
    """
    
    def __init__(self, file_path: str, run = run, progress = progress):
        self.run = run
        self.progress = progress

        self.file_path = file_path
        filesnpaths.is_file_exists(self.file_path)

    def data_vals_sanity_check(self, data_vals: str, current_data_name: str, current_module_num: str):
        """This function checks if the data values were correctly parsed from a line in a KEGG module file.

        This is a sadly necessary step because some KEGG module file lines are problematic and don't follow the right format (ie, 2+ spaces
        between different fields). So here we check if the values that we parsed look like they are the right format, without any extra bits.
        Each data name (ORTHOLOGY, DEFINITION, etc) has a different format to check for.

        Note that we don't check the following data name types: NAME, CLASS, REFERENCE

        WARNING: The error checking and correction is by no means perfect and may well fail when KEGG is next updated. :(

        PARAMETERS
        ==========
        data_vals : str
            the data values field (split from the kegg module line)
        current_data_name : str
            which data name we are working on. It should never be None because we should have already figured this out by parsing the line.
        current_module_num : str
            which module we are working on. We need this to keep track of which modules throw parsing errors.

        RETURNS
        =======
        is_ok : bool
            whether the values look correctly formatted or not
        corrected_vals : str
            if there was a corrected error, this holds the corrected data value field
        corrected_def : str
            if there was a corrected error, this holds the corrected data value field
        parsing_error_type : str
            if there was an error, this describes what it was
        """

        is_ok = True
        is_corrected = False
        corrected_vals = None
        corrected_def = None
        parsing_error_type = None

        if not current_data_name:
            raise ConfigError("data_vals_sanity_check() cannot be performed when the current data name is None. Something was not right "
                              "when parsing the KEGG module line.")
        elif current_data_name == "ENTRY":
            # example format: M00175
            if data_vals[0] != 'M' or len(data_vals) != 6:
                is_ok = False
                parsing_error_type = 'bad_kegg_code_format'
        elif current_data_name == "DEFINITION":
            # example format: (K01647,K05942) (K01681,K01682) (K00031,K00030) (K00164+K00658+K00382,K00174+K00175-K00177-K00176)
            # another example: (M00161,M00163) M00165
            knums = [x for x in re.split('\(|\)|,| |\+|-',data_vals) if x]
            for k in knums:
                if k[0] not in ['K','M'] or len(k) != 6:
                    is_ok = False
            if not is_ok: # this goes here to avoid counting multiple errors for the same line
                parsing_error_type = 'bad_kegg_code_format'
        elif current_data_name == "ORTHOLOGY":
            # example format: K00234,K00235,K00236,K00237
            # more complex example: (K00163,K00161+K00162)+K00627+K00382-K13997
            # another example:  (M00161         [ie, from (M00161  Photosystem II)]
            knums = [x for x in re.split('\(|\)|,|\+|-', data_vals) if x]
            for k in knums:
                if k[0] not in ['K','M'] or len(k) != 6:
                    is_ok = False
            # try to fix it by splitting on first space
            if not is_ok:
                parsing_error_type = 'bad_line_splitting'
                split_data_vals = data_vals.split(" ", maxsplit=1)
                corrected_vals = split_data_vals[0]
                corrected_def = split_data_vals[1]
                # double check that we don't have a knum in the new definition
                if re.match("K\d{5}",corrected_def):
                    corrected_vals = "".join([corrected_vals,corrected_def])
                    corrected_def = None
                is_corrected = True
        elif current_data_name == "PATHWAY":
            # example format: map00020
            if data_vals[0:3] != "map" or len(data_vals) != 8:
                is_ok = False
                parsing_error_type = 'bad_line_splitting'
                split_data_vals = data_vals.split(" ", maxsplit=1)
                corrected_vals = split_data_vals[0]
                corrected_def = split_data_vals[1]
                is_corrected = True
        elif current_data_name == "REACTION":
            # example format: R01899+R00268,R00267,R00709
            rnums = [x for x in re.split(',|\+', data_vals) if x]
            for r in rnums:
                if r[0] != 'R' or len(r) != 6:
                    is_ok = False
            if not is_ok:
                parsing_error_type = 'bad_line_splitting'
                split_data_vals = data_vals.split(" ", maxsplit=1)
                corrected_vals = split_data_vals[0]
                corrected_def = split_data_vals[1]
                is_corrected = True
        elif current_data_name == "COMPOUND":
            # example format: C00024
            if data_vals[0] not in ['C','G'] or len(data_vals) != 6:
                is_ok = False
                parsing_error_type = 'bad_kegg_code_format'
        elif current_data_name == "RMODULE":
            # example format: RM003
            if data_vals[0:2] != "RM" or len(data_vals) != 5:
                is_ok = False
                parsing_error_type = 'bad_kegg_code_format'


        if not is_ok and not is_corrected:
            if self.just_do_it:
                self.progress.reset()
                self.run.warning("While parsing, anvi'o found an uncorrectable issue with a KEGG Module line in module %s, but "
                                 "since you used the --just-do-it flag, anvi'o will quietly ignore this issue and add the line "
                                 "to the MODULES.db anyway. Please be warned that this may break things downstream. In case you "
                                 "are interested, the line causing this issue has data name %s and data value %s."
                                 % (current_module_num, current_data_name, data_vals))
                is_ok = True # let's pretend that everything is alright so that the next function will take the original parsed values

            else:
                raise ConfigError("While parsing, anvi'o found an uncorrectable issue with a KEGG Module line in module %s. The "
                                  "current data name is %s, here is the incorrectly-formatted data value field: %s. If you think "
                                  "this is totally fine and want to ignore errors like this, please re-run the setup with the "
                                  "--just-do-it flag. But if you choose to do that of course we are obliged to inform you that things "
                                  "may eventually break as a result." % (current_module_num, current_data_name, data_vals))

        if is_corrected:
            if anvio.DEBUG and not self.quiet:
                self.progress.reset()
                self.run.warning("While parsing a KEGG Module line, we found an issue with the formatting. We did our very best to parse "
                                 "the line correctly, but please check that it looks right to you by examining the following values.")
                self.run.info("Incorrectly parsed data value field", data_vals)
                self.run.info("Corrected data values", corrected_vals)
                self.run.info("Corrected data definition", corrected_def)

        return is_ok, corrected_vals, corrected_def, parsing_error_type
