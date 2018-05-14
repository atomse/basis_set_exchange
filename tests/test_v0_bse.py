"""
Compares version 0 with historical BSE
"""

import os
import re
import bz2
import pytest
import bse

# Find the dir with all the bse files
_my_dir = os.path.dirname(os.path.abspath(__file__))
_hist_data_dir = os.path.join(_my_dir, 'basis_set_exchange_historical')
_bse_data_dir = os.path.join(_hist_data_dir, 'bse-formatted')
_hist_testfile = os.path.join(_hist_data_dir, '.is_historical')
_hist_testfile_exists = os.path.isfile(_hist_testfile)

# Skip everying in this file if the submodule isn't checked out
pytestmark = pytest.mark.skipif(_hist_testfile_exists != True, reason="Historical basis data not downloaded")

# Load all the metadata once
_bs_metadata = bse.get_metadata()
_bs_formats = list(bse.get_formats().keys())

# Only the names with a version zero
_bs_names_only_v0 = [x for x,y in _bs_metadata.items() if 0 in y['versions']]

# Read the mapping of new BSE names to old BSE files
with open(os.path.join(_my_dir, 'bse_v0_map.txt'), 'r') as f:
    _bse_v0_map = dict(re.split('\t+', x.strip()) for x in f.readlines())

# Mapping of new->old symbols    
_sym_replace_map = { 'Uun': 'Ds', 'UUN': 'DS',
                     'Uuu': 'Rg', 'UUU': 'RG',
                     'Uub': 'Cn', 'UUB': 'CN',
                     'Uut': 'Nh', 'UUT': 'NH',
                     'Uuq': 'Fl', 'UUQ': 'FL',
                     'Uup': 'Mc', 'UUP': 'MC',
                     'Uuh': 'Lv', 'UUH': 'LV',
                     'Uus': 'Ts', 'UUS': 'TS',
                     'Uuo': 'Og', 'UUO': 'OG'
                   }

def _process_commonline(x):
    x = x.strip()

    # collapse multiple spaces
    x = re.sub(r' +', r' ', x)

    # remove trailing zero after a decimal point
    #x = re.sub(r'\.(\d+?)0+\b', r'.\1 ', x)
    #x = re.sub(r'\.(\d+?)0+([Ee])', r'.\1\2', x)

    # Substitute old symbols (BSE had old symbols for some elements)
    for k,v in _sym_replace_map.items():
        x = x.replace(k, v)

    # Replace D with E for exponents
    x = re.sub(r'(\d)D([\+\-]?)(\d)', r'\1E\2\3', x)

    return x


def _process_nwchem(lines):
    # Process lines from an nwchem-formatted file
    lines = [ _process_commonline(x) for x in lines ]

    # Remove comments and empty lines
    lines = [ x for x in lines if not x.startswith('#') and x != '']

    return lines


def _process_gaussian(lines):
    # Process lines from an g94-formatted file
    lines = [ _process_commonline(x) for x in lines ]

    # The 'potential' lines are just comments (but have to be there)
    lines = [ re.sub(r'^([spdfghijk]|ul)[ \-].*potential$', r'', x) for x in lines ]

    # Remove comments and empty lines
    lines = [ x for x in lines if not x.startswith('!') and x != '']

    

    return lines


def _lines_equivalent(line1, line2):
    # Bail early if they are exactly the same
    if line1 == line2:
        return True

    # Split the string by spaces, and compare
    splt1 = re.split(r' +', line1)
    splt2 = re.split(r' +', line2)

    if len(splt1) != len(splt2):
        return False

    for i in range(len(splt1)):
        # See if they are floats and do exact compare
        try:
            x1 = float(splt1[i])
            x2 = float(splt2[i])
            if x1 != x2:
                return False
        except ValueError:
            if splt1[i] != splt2[i]:
                return False

    return True

# Maps formats to processing functions and bse suffixes
_format_map = { 'nwchem' : ('NWChem', _process_nwchem),
                'gaussian94' : ('Gaussian94', _process_gaussian)
              }

@pytest.mark.parametrize('basis_name', _bs_names_only_v0)
@pytest.mark.parametrize('fmt', ['nwchem', 'gaussian94'])
def test_v0_with_bse(basis_name, fmt):
    basis_meta = _bs_metadata[basis_name]
    fmt_info = _format_map[fmt]

    # It's ok if the basis doesn't have v0. That means it wasn't in the old BSE
    if not 0 in basis_meta['versions']:
        print("Basis set {} doesn't have a version 0".format(basis_name))
        return

    if not basis_name in _bse_v0_map:
        raise RuntimeError("Mapping from BSE to old BSE name doesn't exist for " + basis_name)

    # Read in the data from the old BSE
    bse_name = _bse_v0_map[basis_name]
    fmt_suffix = '.' + fmt_info[0] + '.bz2'
    bse_file = os.path.join(_bse_data_dir, bse_name + fmt_suffix)
    if not os.path.isfile(bse_file):
        raise FileNotFoundError("File {} does not exist (for comparing basis {})".format(bse_file, basis_name))

    with bz2.open(bse_file, 'rt') as f:
        bse_data = f.readlines()
    bse_data = fmt_info[1](bse_data)

    # read in data from the new bse (version 0)
    new_data = bse.get_basis_set(basis_name, version=0, fmt=fmt)
    new_data = new_data.split('\n')
    new_data = fmt_info[1](new_data)

    if len(new_data) != len(bse_data):
        raise RuntimeError("Basis set: {} different number of lines: {} vs {}".format(basis_name, len(new_data), len(bse_data)))

    for i in range(len(new_data)):
        new_line = new_data[i]
        bse_line = bse_data[i]

        if not _lines_equivalent(new_line, bse_line):
            errstr = '''Difference found. Line {}
                        New: {}
                        Old: {}'''.format(i, new_line, bse_line)
            raise RuntimeError(errstr)
