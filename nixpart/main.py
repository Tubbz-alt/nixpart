import os
import re
import sys
import argparse
import logging
import subprocess

from xml.etree import ElementTree

from nixpart.storage import realize

XMLDECL_RE = re.compile(r'<\?xml.*?>')


class NixDecodeError(Exception):
    pass


def xml2python(xml):
    """
    Turn an XML document generated by 'nix-instantiate --xml' into native
    Python types.
    """
    if xml.tag == 'attrs':
        attrset = {}
        for child in xml:
            for subchild in child:
                attrset[child.attrib['name']] = xml2python(subchild)
        return attrset
    elif xml.tag == 'list':
        return [xml2python(child) for child in xml]
    elif xml.tag in ('string', 'path'):
        return xml.attrib['value']
    elif xml.tag == 'bool':
        return xml.attrib['value'] == "true"
    elif xml.tag == 'null':
        return None
    elif xml.tag == 'int':
        return int(xml.attrib['value'])
    else:
        msg = "Unknown type {0} in instantiated expression.".format(xml.tag)
        raise NixDecodeError(msg)


def nix2python(path):
    """
    Evaluate the Nix expression file given by path and return it as dict
    consisting of native Python types.
    """
    expr = r'''
      let
        cfg = (import <nixpkgs/nixos/lib/eval-config.nix> {{
          modules = [ {} ];
        }}).config;
      in {{ inherit (cfg) storage fileSystems swapDevices; }}
    '''.format(path)
    cmd = ['nix-instantiate', '--eval-only', '--strict', '--xml', '-E', expr]
    output = subprocess.check_output(cmd)
    xml = ElementTree.fromstring(output)
    if xml.tag != 'expr':
        msg = "Instantiated Nix expression doesn't have a root <expr> element."
        raise NixDecodeError(msg)
    return xml2python(xml[0])


def handle_nixos_config(path):
    fullpath = os.path.abspath(path)
    if not os.path.exists(fullpath):
        msg = "{} does not exist.".format(fullpath)
        raise argparse.ArgumentTypeError(msg)
    return fullpath


def main():
    desc = "Declaratively create partitions and filesystems"
    parser = argparse.ArgumentParser(description=desc)

    parser.add_argument(
        '-v', '--verbose', dest='verbosity', action='count', default=0,
        help="Print what's going on, use multiple times to increase verbosity"
    )

    parser.add_argument(
        '-X', '--from-xml', dest='is_xml', action='store_true',
        help="The NixOS config file in XML format"
    )

    parser.add_argument(
        'nixos_config', type=handle_nixos_config,
        help="A NixOS configuration expression file"
    )

    args = parser.parse_args()

    if args.verbosity > 0:
        pass  # TODO!

    if args.is_xml:
        rawxml = open(args.nixos_config, 'r').read()
        xml = ElementTree.fromstring(XMLDECL_RE.sub('', rawxml))
        if xml.tag != 'expr':
            msg = "Nix XML tree doesn't have a root <expr> element."
            raise NixDecodeError(msg)
        expr = xml2python(xml[0])
    else:
        expr = nix2python(args.nixos_config)

    realize(expr)
