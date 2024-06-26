from .structures import Handler, Exchange, Loop, Update
import corvutils.pyparsing as pp
import os, sys, subprocess

# Debug: FDV
import pprint
pp_debug = pprint.PrettyPrinter(indent=4)

# Naming grammar for *.files: [xcNum].[tool].[description].files
#filesGrammar = pp.delimitedList(pp.Word(pp.alphanums), delim='.')

# Define dictionary of implemented calculations
implemented = {}

# The following are the basic requirement for even the most minimal VASP
# calculation.
basics = ['title','cell_scaling','cell_vectors','natoms','cell_red_xyz','cell_red_opt_flags','pspfiles']
strlistkey = lambda L:','.join(sorted(L))
subs = lambda L:[{L[j] for j in range(len(L)) if 1<<j&k} for k in range(1,1<<len(L))]
for s in subs(['ene_int']):
    key = strlistkey(s)
    autodesc = 'Get ' + ', '.join(s) + ' using VASP'
    input = basics
    cost =  2
    implemented[key] = {'type':'Exchange','out':list(s),'req':input,
                        'desc':autodesc,'cost':cost}

# Debug: FDV
#pp_debug.pprint(implemented)
#sys.exit()

class Vasp(Handler):
    def __str__(self):
        return 'VASP Handler'

    @staticmethod
    def canProduce(output):
        if isinstance(output, list) and output and isinstance(output[0], str):
            return strlistkey(output) in implemented
        elif isinstance(output, str):
            return output in implemented
        else:
            raise TypeError('Output should be token or list of tokens')

    @staticmethod
    def requiredInputFor(output):
        if isinstance(output, list) and output and isinstance(output[0], str):
            unresolved = {o for o in output if not Vasp.canProduce(o)}
            canProduce = (o for o in output if Vasp.canProduce(o))
            additionalInput = (set(implemented[o]['req']) for o in canProduce)
            return list(set.union(unresolved,*additionalInput))
        elif isinstance(output, str): 
            if output in implemented:
                return implemented[output]['req']
            else:
                return [output]
        else:
            raise TypeError('Output should be token or list of tokens')

    @staticmethod
    def costOf(output):
        if isinstance(output, list) and output and isinstance(output[0], str):
            key = strlistkey(output)
        elif isinstance(output, str):
            key = output
        else:
            raise TypeError('Output should be token or list of tokens')
        if key not in implemented:
            raise LookupError('Corvus cannot currently produce ' + key + ' using VASP')
        return implemented[key]['cost']

    @staticmethod
    def sequenceFor(output,inp=None):
        if isinstance(output, list) and output and isinstance(output[0], str):
            key = strlistkey(output)
        elif isinstance(output, str):
            key = output
        else:
            raise TypeError('Output should be token or list of tokens')
        if key not in implemented:
            raise LookupError('Corvus cannot currently produce ' + key + ' using VASP')
        f = lambda subkey:implemented[key][subkey]
        if f('type') == 'Exchange':
            return Exchange(Vasp, f('req'), f('out'), cost=f('cost'), desc=f('desc'))
        
    @staticmethod
    def prep(config):
        subdir = config['pathprefix'] + str(config['xcIndex']) + '_VASP'
        xcDir = os.path.join(config['cwd'], subdir)
        # Make new output directory if it doesn't exist
        if not os.path.exists(xcDir):
            os.mkdir(xcDir)
        # Remove any old output files
        else :
            for file in os.listdir(xcDir):
                if file.endswith('.out'):
                    os.remove(os.path.join(xcDir, file))
        # Store current Exchange directory in configuration
        config['xcDir'] = xcDir
    
    @staticmethod
    def generateInput(config, input, output):

# Debug: FDV
#       pp_debug.pprint(input)
#       pp_debug.pprint(output)
#       sys.exit()

# Start with the preparation of the POTCAR since that is needed for all
# calculations

# In VASP the order of the content of the POTCAR and that of the POSCAR are
# related, so we have to be careful on how we order things and we need to
# remember that order for future calculations.

# First we parse cell_red_xyz to find the atom labels

# Debug: FDV
        print(input)
        sys.exit()
        
        # Switch based on what output is required
        files = []
        dir = config['xcDir']
        ppFilelist = pp.OneOrMore(pp.Word(pp.printables)) 
        pseudos = ppFilelist.parseString(input['pspfiles']).asList()

        # Lattice optimization
        if set(output.keys()) == set(['aopt']):
            filebase = '0.abinit.opt'
            pathbase = os.path.join(dir, filebase)
            abinitFileList = abinitFiles(pathbase, pseudos)
            writeList(abinitFileList, pathbase + '.files')
            writeDict(optInput(input), pathbase + '.in')
            files.append(filebase + '.files')

        # Symmetry-reduced q-grid for use with ANADDB 
        elif set(output.keys()) == set(['qptlist']):
            filebase = '0.abinit.qgrid'
            pathbase = os.path.join(dir, filebase)
            abinitFileList = abinitFiles(pathbase, pseudos)
            writeList(abinitFileList, pathbase + '.files')
            writeDict(qgridInput(input), pathbase + '.in')
            files.append(filebase + '.files')

        # Internal energy
        elif set(output.keys()) ==set(['eint']):
            filebase = '1.abinit.U'
            pathbase = os.path.join(dir, filebase)
            abinitFileList = abinitFiles(pathbase, pseudos)
            writeList(abinitFileList, pathbase + '.files')
            writeDict(UInput(input), pathbase + '.in') 
            files.append(filebase + '.files')

        # Electron-phonon calculation using ANADDB
        elif set(output.keys()).issubset(set(['pdos','a2f','a2','dynmat','eint'])):
            filebase = '1.abinit.elphon'
            pathbase = os.path.join(dir, filebase)
            abFileList = abinitFiles(pathbase, pseudos)
            writeList(abFileList,  pathbase + '.files')
            writeDict(elphonInput(input), pathbase + '.in')
            dsPrefix = abFileList[3] + '_DS'
            files.append(filebase + '.files')
            
            filebase = '2.mrgddb.elphon'
            pathbase = os.path.join(dir, filebase)
            qptRange = list(range(3, 3 + len(input['qptlist'])))
            ddbFileList = ddbFiles(pathbase, dsPrefix, qptRange)
            writeList(ddbFileList, pathbase + '.files')
            files.append(filebase + '.files')

            filebase = '3.mrggkk.elphon'
            pathbase = os.path.join(dir, filebase)
            atdirRange = list(range(1, 1 + 3*int(input['natom'])))
            gkkFileList = gkkFiles(pathbase, dsPrefix, qptRange, atdirRange)
            writeList(gkkFileList, pathbase + '.files')
            files.append(filebase + '.files')
            
            filebase = '4.anaddb.ifc'
            pathbase = os.path.join(dir, filebase)
            anaFileList = anaddbFiles(pathbase, ddbFileList[0], gkkFileList[0]) 
            writeList(anaFileList, pathbase + '.files')
            writeDict(ifcInput(input), pathbase + '.in')
            files.append(filebase + '.files')

        # Return ordered list of *.files
        return files
    
    @staticmethod
    def run(config, files):
        # Run by looping through input files
        dir = config['xcDir']
        for f in files:
            (num, tool, desc, suffix) = filesGrammar.parseString(f)
            if config['parallelRun']:
                if tool == 'abinit':
                    prefix = config['parallelRun']
                else:
                    prefix = config['parallelRun'].split()[0] + ' -n 1' 
            else:
                prefix = ''
            executable = (prefix + ' ' + config[tool]).split()
                
            inp = open(os.path.join(dir, f), 'r')
            log = open(os.path.join(dir, '.'.join(['log', num, desc, tool])), 'w')
            p = subprocess.run(executable, cwd=dir, stdin=inp, stdout=log, stderr=log)
            inp.close()
            log.close()
    
    @staticmethod
    def translateOutput(config, input, output): 
        dir = config['xcDir']
        for target in output:
            if target == 'aopt':
                file = os.path.join(dir, '0.abinit.opt.out')
                output[target] = getacell(file)
            elif target == 'acell-grid':
                num = int(check(input, 'nagrid', default=9))
                output[target] = getagrid(input['acell'], num)
            elif target == 'qptlist':
                file = os.path.join(dir, '0.abinit.qgrid.out')
                output[target] = kgrid2qgrid(file)
            elif target == 'eint':
                if set(output) == {'eint'}:
                    file = os.path.join(dir, '1.abinit.U.out')
                    output[target] = getU(file)
                elif len(set(output).intersection({'dynmat','pdos','a2','a2f'})) > 0:
                    file = os.path.join(dir, '1.abinit.elphon.out')
                    output[target] = getU(file, addDS='1')
            elif target == 'pdos':
                file = os.path.join(dir, '4.anaddb.ifc.out_ep_PDS')
                output[target] = anaddb2cols(file)
            elif target == 'a2f':
                file = os.path.join(dir, '4.anaddb.ifc.out_ep_A2F')
                output[target] = anaddb2cols(file)
            elif target == 'a2':
                file = os.path.join(dir, '4.anaddb.ifc.out_ep_')
                output[target] = eli2couplings(file) 
            elif target == 'dynmat':
                file = os.path.join(dir, 'ifcinfo.out')
                output[target] = ifc2dym(file, input)
    
    @staticmethod
    def cleanup(config):    
        dir = config['xcDir']
        for file in os.listdir(dir):
            if 'CLEANUP' in file:
                os.remove(os.path.join(dir, file))

##### Generic Helper Methods ##########
def check(input, token, default=None):
    if token in input:
        return input[token]
    else:
        return default

def writeDict(inDict, filename):
    with open(filename, 'w') as file:
        for token, value in iter(sorted(inDict.items())):
            file.write(token + ' ' + str(value) + '\n')

def writeList(list, filename):
    with open(filename, 'w') as file:
        for line in list:
            file.write(line + '\n') 

def expandedList(string, length=3):
    assert isinstance(string, str)
    value = pp.Word(pp.nums + ".+-E")
    prefix = pp.Combine(pp.Optional(pp.Word(pp.nums)) + pp.Literal('*'))
    numList = pp.OneOrMore(pp.Optional(prefix) + value)
    expanded = []
    num = 1
    for x in numList.parseString(string).asList():
        if num is not 1:
            expanded.extend([x]*num)
            num = 1
        elif '*' in x:
            if x[:-1] is '':
                num = length
            else:
                num = int(x[:-1])
        else:
            expanded.append(x)
    return expanded
    
#### Specific Input Methods #########
def abinitFiles(abPrefix, pspList):
    files = []
    files.append(abPrefix + '.in')
    files.append(abPrefix + '.out')
    files.append(abPrefix + '.i')
    files.append(abPrefix + '.o')
    files.append(abPrefix + '.CLEANUP')
    # Get absolute file location(s)
    for psp in pspList:
        files.append(os.path.abspath(psp))
    return files

def ddbFiles(mddbPrefix, datasetPrefix, qptRange):
    files = []
    files.append(mddbPrefix + '.MDDB')
    files.append('Merged Derivative Database')
    files.append(str(len(qptRange)))
    for i in qptRange:
        files.append(datasetPrefix + str(i) + '_DDB')
    return files

def gkkFiles(mgkkPrefix, datasetPrefix, qptRange, atdirRange):
    files = []
    files.append(mgkkPrefix + '.MGKK_bin')
    files.append('0  # binary output')
    files.append(datasetPrefix + '2_WFK')
    numfiles = len(qptRange)*len(atdirRange)
    files.append(' '.join(['0', str(numfiles), str(numfiles)]))
    for i in qptRange:
        for j in atdirRange:
            files.append(datasetPrefix + str(i) + '_GKK' + str(j))
    return files

def anaddbFiles(anaPrefix, mddbFile, mgkkFile):
    files = []
    files.append(anaPrefix + '.in')
    files.append(anaPrefix + '.out')
    files.append(mddbFile)
    files.append(anaPrefix + '.band2eps')
    files.append(mgkkFile)
    files.append(anaPrefix + '.dummyLine1')
    files.append(anaPrefix + '.dummyLine2')
    return files

def baseInput(input):
    dict = {}
    dict['acell'] = input['acell']
    dict['rprim'] = input['rprim']
    dict['natom'] = input['natom']
    dict['ntypat'] = input['ntypat']
    dict['typat'] = input['typat']
    dict['znucl'] = input['znucl']
    dict['xred'] = input['xred']
    return dict

def optInput(input):
    dict = baseInput(input)
    dict['diemac'] = check(input, 'diemac', default='1.0E+06')
    dict['tolvrs'] = check(input, 'tolvrs', default='1.0E-18')
    dict['kptopt'] = check(input, 'kptopt', default=1)
    dict['ngkpt'] = check(input, 'ngkpt', default='4 4 4')
    dict['nshiftk'] = check(input, 'nshiftk', default=1)
    dict['shiftk'] = check(input, 'shiftk', default='0 0 0')
    dict['istwfk'] = check(input, 'istwfk', default='*1')
    dict['ixc'] = check(input, 'ixc', default=7)
    dict['ecut'] = check(input, 'ecut', default=50.0)
    dict['ecutsm'] = check(input, 'ecutsm', default=3.0)
    # If no ecut/ecutsm provided use defaults AND store in System
    #   for consistent usage in subsequent calculations
    input['ecut'] = dict['ecut']
    input['ecutsm'] = dict['ecutsm']
    dict['optcell'] = check(input, 'optcell', default=1)
    dict['ionmov'] = check(input, 'ionmov', default=3)
    dict['ntime'] = check(input, 'ntime', default=20)
    dict['dilatmx'] = check(input, 'dilatmx', default=1.05)
    dict['iscf'] = check(input, 'iscf', default=5)
    dict['nstep'] = check(input, 'nstep', default=50)
    if 'verbatim' in input:
        dict[''] = input['verbatim']
    return dict

def qgridInput(input):
    dict = baseInput(input)
    dict['kptopt'] = 1
    dict['ngkpt'] = input['ngqpt']
    dict['nshiftk'] = 1
    dict['shiftk'] = '0 0 0'
    dict['prtvol'] = -1
    dict['ecut'] = 10.0
    return dict

def UInput(input):
    dict = baseInput(input)
    dict['toldfe'] = check(input, 'toldfe', default='1.0d-12')
    dict['nstep'] = check(input, 'nstep', default=50)
    dict['ngkpt'] = check(input, 'ngkpt', default='4 4 4')
    dict['nshiftk'] = check(input, 'nshiftk', default=1)
    dict['shiftk'] = check(input, 'shiftk', default='0 0 0')
    dict['ecut'] = check(input, 'ecut', default=50.0)
    dict['ixc'] = check(input, 'ixc', default=7)
    dict['istwfk'] = check(input, 'istwfk', default='*1')
    if 'verbatim' in input:
        dict[''] = input['verbatim']
    return dict

def elphonInput(input):
    dict = baseInput(input)
    qpts = input['qptlist']
    dict['ndtset'] = 2 + len(qpts)
    # Density calculation
    dict['tolvrs1'] = check(input, 'tolvrs1', default='1.0d-18')
    dict[ 'nline1'] = check(input, 'nline1', default=8)
    dict['rfphon1'] = 0
    dict[  'nqpt1'] = 0
    dict['getwfk1'] = 0
    dict['prtden1'] = 1
    dict['kptopt1'] = 1
    # Wavefunction calculation
    dict['tolwfr2'] = check(input, 'tolwfr2', default='1.0d-22')
    dict[  'iscf2'] = check(input, 'iscf2', default=-3)
    dict['rfphon2'] = 0
    dict[  'nqpt2'] = 0
    dict['getwfk2'] = 0
    dict['getden2'] = 1
    dict[ 'prtwf2'] = 1
    # Calculation for each qpt
    for i, qpt in enumerate(qpts):
        dict['qpt' + str(i+3)] = qpt
    dict[    'ixc'] = check(input, 'ixc', default=7)
    dict[ 'diemac'] = check(input, 'diemac', default='1.0E+06')
    dict[ 'tolvrs'] = check(input, 'tolvrs', default='1.0e-10')
    dict[ 'istwfk'] = '*1'
    dict[ 'rfphon'] = 1
    dict[   'nqpt'] = 1
    dict[  'rfdir'] = '1 1 1'
    dict['rfatpol'] = '1 ' + str(input['natom'])
    dict[  'prtwf'] = 0
    dict[ 'getwfk'] = 2
    dict['prepgkk'] = 1
    dict[ 'prtgkk'] = 1
    dict[ 'kptopt'] = 3
    dict[  'ngkpt'] = check(input, 'ngkpt', default='4 4 4')
    dict['nshiftk'] = 1
    dict[ 'shiftk'] = '0.0 0.0 0.0'
    dict[   'ecut'] = check(input, 'ecut', default='50.0')
    if 'ecutsm' in input:
        dict['ecutsm'] = input['ecutsm']
    dict[  'nstep'] = check(input, 'nstep', default=800)
    if 'verbatim' in input:
        dict[''] = input['verbatim']
    return dict

def ifcInput(input):
    dict = {}
    dict[ 'elphflag'] = 1
    dict[   'prtdos'] = 1
    dict[  'prt_ifc'] = 1
    dict[  'ifcflag'] = 1
    dict[   'ifcana'] = 1
    dict[   'ifcout'] = check(input, 'ifcout', default=200) #TODO: create shell/nifc function
    dict[   'natifc'] = input['natom']
    dict[    'atifc'] = ' '.join(str(i) for i in range(1, 1 + int(input['natom'])))
    dict[    'ngqpt'] = check(input, 'ngqpt', default='4 4 4')
    dict[   'ng2qpt'] = check(input, 'ng2qpt', default='16 16 16')
    dict[      'asr'] = check(input, 'asr', default=2)
    dict['symdynmat'] = check(input, 'symdynmat', default=0)
    dict[    'nph1l'] = check(input, 'nph1l', default=1)
    dict[    'qph1l'] = check(input, 'qph1l', default='0.0 0.0 0.0 1')
    dict[   'nqpath'] = check(input, 'nqpath', default=5)
    qpaths = '0.0 0.0 0.0\n0.0 0.0 1/8\n0.0 0.0 1/4\n 0.0 0.0 1/2\n0.0 0.0 1\n'
    dict[    'qpath'] = check(input, 'qpath', default=qpaths)
    dict[   'mustar'] = check(input, 'mustar', default=0.1)
    return dict

#### Specific Translation Methods #########
def getacell(file):
    token = pp.Keyword('acell')
    vector = pp.Group(pp.Word(pp.nums + ".+-E")*3)
    end = pp.Literal('END DATASET(S)')
    acell = (pp.SkipTo(end) + pp.SkipTo(token) + token).suppress() + vector
    f = open(file, 'r')
    try:
        a = acell.parseString(f.read()).asList()[0]
    except pp.ParseException as pe:
        print(('Parsing Error using pyparsing: invalid input:', pe))
        sys.exit()
    f.close()
    return '  '.join(a)

def getagrid(acell, n):
    if isinstance(acell, str): 
        a0 = list(map(float, expandedList(acell)))
    start = 0.98
    end = 1.03
    step = (end - start) / (n - 1.0)
    grid = []
    for i in range(n):
        scale = start + i * step
        grid.append('  '.join([str(x * scale) for x in a0]))
    return grid

def getU(file, addDS=''):
    token = pp.Literal('etotal' + addDS)
    value = pp.Word(pp.nums + ".+-E")
    end = pp.Literal('END DATASET(S)')
    etotal = (pp.SkipTo(end) + pp.SkipTo(token) + token).suppress() + value
    f = open(file, 'r')
    try:
        u = etotal.parseString(f.read()).asList()[0]
    except pp.ParseException as pe:
        print(('Parsing Error using pyparsing: invalid input:', pe))
        sys.exit()
    f.close()
    return float(u)

def kgrid2qgrid(file):
    token = pp.Keyword('kpt')
    qpt = pp.Group(pp.Word(pp.nums + ".+-E")*3)
    kpt = (pp.SkipTo(token) + token).suppress() + pp.OneOrMore(qpt)
    f = open(file, 'r')
    try:
        pts = kpt.parseString(f.read()).asList()
    except pp.ParseException as pe:
        print(("Parsing Error using pyparsing: invalid input:", pe))
        sys.exit()
    f.close()
    qpts = []
    for p in pts:
        qpts.append(' '.join(p))
    return qpts

def anaddb2cols(file):
    header = pp.OneOrMore(pp.pythonStyleComment)
    pt = pp.Group(pp.Word(pp.nums + ".+-E") * 2)
    text = header.suppress() + pp.OneOrMore(pt)
    f = open(file, 'r')
    try:
        data = text.parseString(f.read()).asList()
    except pp.ParseException as pe:
        print(("Parsing Error using pyparsing: invalid input:", pe))
        sys.exit()
    f.close() 
    return list(map(list, list(zip(*data))))

def eli2couplings(filePrefix):
    header = pp.OneOrMore(pp.pythonStyleComment)
    pt = pp.Group(pp.Word(pp.nums + ".+-E") * 2)
    text = header.suppress() + pp.OneOrMore(pt)
    pdsFile = open(filePrefix + 'PDS', 'r')
    a2fFile = open(filePrefix + 'A2F', 'r')
    try:
        pdsRow = text.parseString(pdsFile.read()).asList()
        a2fRow = text.parseString(a2fFile.read()).asList()
    except pp.ParseException as pe:
        print(('Parsing Error using pyparsing: invalid input:', pe))
        sys.exit()
    pdsFile.close()
    a2fFile.close()
    enCol = list(map(list, list(zip(*pdsRow))))[0]
    pdsCol = list(map(list, list(zip(*pdsRow))))[1]
    a2fCol = list(map(list, list(zip(*a2fRow))))[1]
    couplings = [enCol,[]]
    for i, pds in enumerate(pdsCol):
        if float(pds) == 0.0:
            couplings[1].append(0.0)
        else:
            couplings[1].append( float(a2fCol[i]) / float(pds) )
    return couplings

def ifc2dym(file, input):
    from decimal import Decimal, ROUND_UP
    import math
    index = pp.Word(pp.nums)
    vector = pp.Group(pp.Word(pp.nums + ".+-E")*3)
    matrix = pp.Group(vector * 3)
    ifcblock = pp.Group(index*2 + vector + matrix)
    text = pp.OneOrMore(ifcblock)
    f = open(file, 'r')
    try:
        data = text.parseString(f.read()).asList()
    except pp.ParseException as pe:
        print(('Parsing Error using pyparsing: invalid input:', pe))
        sys.exit()
    f.close()
    natom = int(data[-1][0])
    # if natom is not int()  # check natom against System?
    nifc = int(data[-1][1])

    # Create and fill ifcInfo data structure
    ifcInfo = [[{} for b in range(nifc)] for a in range(natom)]
    for info in data:
        atomIndex = int(info[0]) - 1
        ifcIndex = int(info[1]) - 1 
        atomPos = list(map(float, info[2]))
        ifcMatrix= [list(map(float, row)) for row in info[3]]
        ifcInfo[atomIndex][ifcIndex] = {'pos':atomPos,'ifc':ifcMatrix} 

    # Convert VASP input strings into indexed numerical data
    acell = list(map(float, expandedList(input['acell'])))
    try:
        parsedMatrix = matrix.parseString(input['rprim']).asList()[0]
        rprim = [list(map(float, row)) for row in parsedMatrix]
    except pp.ParseException as pe:
        print(('Parsing Error using pyparsing: invalid input:', pe))
        sys.exit()
    znucl = list(map(int, expandedList(input['znucl'], length=natom)))
        
    ncluster = 300.0
    n = int(math.ceil((pow(ncluster/natom, 1.0/3.0) - 1.0) / 2.0))
    copyRange = list(range(-n, n+1))
    copyGrid = ((i,j,k) for i in copyRange for j in copyRange for k in copyRange)

    # Build cluster
    cluster = []
    for ijk in copyGrid:
        dx = [a*sum(i*c for i,c in zip(ijk,row)) for row, a in zip(rprim,acell)]
        for iAt in range(natom):
            clusterAtom = {'cellIndex':iAt}
            cellCoord = list(map(float, ifcInfo[iAt][0]['pos']))
            clusterAtom['coord'] = list(map(sum, list(zip(cellCoord, dx)))) 
            clusterAtom['dist'] = math.sqrt(sum(a*a for a in clusterAtom['coord']))
            clusterAtom['Z'] = znucl[iAt]
            clusterAtom['mass'] = amu[znucl[iAt]]
            if all(i is 0 for i in ijk):
                clusterAtom['central'] = True
            cluster.append(clusterAtom)
    ru8 = lambda x: Decimal(x).quantize(Decimal('0.12345678'),rounding=ROUND_UP)
    cluster.sort(key=lambda atom:(ru8(atom['dist']), 
                                  atom['cellIndex'],
                                  ru8(atom['coord'][0]),
                                  ru8(atom['coord'][1]),
                                  ru8(atom['coord'][2])
                                 ))
    ncluster = len(cluster)

    # Get distance/displacement for cluster pairs used for geometric matching
    clustPair = [[{} for j in range(ncluster)] for i in range(ncluster)]
    for i,j in ((i,j) for i in range(ncluster) for j in range(i,ncluster)):
        if i is j:
            clustPair[i][j]['dist'] = 0.0
            clustPair[i][j]['xi-xj'] = [0.0, 0.0, 0.0]
        else:
            displ = list(map(lambda x,y:x-y, cluster[i]['coord'], cluster[j]['coord']))
            clustPair[i][j]['dist'] = math.sqrt(sum(x*x for x in displ))
            clustPair[j][i]['dist'] = clustPair[i][j]['dist']
            clustPair[i][j]['xi-xj'] = displ
            clustPair[j][i]['xi-xj'] = [-x for x in displ]

    # Get distance/displacement for reference pairs used for geometric matching
    refPair = [[{} for b in range(nifc)] for a in range(natom)]
    for a,b in ((a,b) for a in range(natom) for b in range(nifc)):
        displ = list(map(lambda x,y:x-y, ifcInfo[a][0]['pos'], ifcInfo[a][b]['pos']))
        refPair[a][b]['dist'] = math.sqrt(sum(x*x for x in displ))
        refPair[a][b]['xa0-xab'] = displ

    # Start building a type-2 DYM dict
    dym = {'dymType':2} 
    
    # Section 1: Number of atoms in cluster
    dym['nAt'] = ncluster
    
    # Section 2: List of atomic numbers for each atom in cluster
    dym['atNums'] = [atom['Z'] for atom in cluster]

    # Section 3: List of atomic masses for each atom in cluster
    dym['atMasses'] = [atom['mass'] for atom in cluster]

    # Section 4: List of positions for each atom in cluster
    dym['atCoords'] = [atom['coord'] for atom in cluster]

    # Section 5: 3x3 block of dynamical matrix for each pair of atoms in cluster
    maxDiff = 0.001
    cutoffDist = 10.0
    areClose = lambda x,y: abs(x-y) <= maxDiff
    dym['dm'] = [[None for j in range(ncluster)] for i in range(ncluster)]
    for i,j in ((i,j) for i in range(ncluster) for j in range(ncluster)):
        dist = clustPair[i][j]['dist']
        displ = clustPair[i][j]['xi-xj']
        if dist > cutoffDist:
            dym['dm'][i][j] = [[0.0]*3]*3
        else:
            found = False
            # Loop over reference pairs of same original cell index
            atomCellIndex = cluster[i]['cellIndex']
            for b,refPairB in enumerate(refPair[atomCellIndex]):
                refDist = refPairB['dist']
                refDispl = refPairB['xa0-xab']
                # Found reference pair with same geometry
                if areClose(dist, refDist) and all(map(areClose, displ, refDispl)):
                    clustPair[i][j]['refifc'] = b
                    dym['dm'][i][j] = ifcInfo[atomCellIndex][b]['ifc']
                    found = True
                # At end of reference list with no match found
            if not found:
                raise Exception('Error: cannnot find reference for pair ' + str((i+1,j+1)))
    
    # Ordering of cluster atoms for printing purposes
    dym['printOrder'] = list(range(ncluster))

    # Section Type-2: Info for central cell atoms
    typat = list(map(int, expandedList(input['typat'], length=natom)))
    dym['nTypeAt'] = len(set(typat))
    dym['nCellAt'] = natom
    dym['centerAt'] = {z:[] for z in znucl}
    for i,atom in ((i,a) for i,a in enumerate(cluster) if 'central' in a):
        atomInfo = {'clustIndex':i}
        atomInfo.update({k:atom[k] for k in ('cellIndex','coord')})
        dym['centerAt'][atom['Z']].append(atomInfo)

    return dym

def nifc(acell, rprim, cutoff=10.0):
    import math
    dxBasis = [[r*a for r in col] for col, a in zip(list(zip(*rprim)),acell)]
    minDist = math.sqrt(min(sum(x*x for x in dx) for dx in dxBasis))
    nord = int(math.ceil(cutoff/minDist))
    iRange = list(range(-nord, nord+1))
    grid = ((i,j,k) for i in iRange for j in iRange for k in iRange)
    count = 0
    for ijk in grid:
        dx = [a*sum(i*c for i,c in zip(ijk,row)) for row, a in zip(rprim,acell)]
        dist = math.sqrt(sum(a*a for a in dx))
        if dist < cutoff:
            count += 1
    return count

# Atomic mass table from ABINIT
amu = {}
amu.update({  1:1.00794,    2:4.002602,   3:6.941,      4:9.012182,    5:10.811})
amu.update({  6:12.011,     7:14.00674,   8:15.9994,    9:18.9984032, 10:20.1797})
amu.update({ 11:22.989768, 12:24.3050,   13:26.981539, 14:28.0855,    15:30.973762})
amu.update({ 16:32.066,    17:35.4527,   18:39.948,    19:39.0983,    20:40.078})
amu.update({ 21:44.955910, 22:47.88,     23:50.9415,   24:51.9961,    25:54.93805})
amu.update({ 26:55.847,    27:58.93320,  28:58.69,     29:63.546,     30:65.39})
amu.update({ 31:69.723,    32:72.61,     33:74.92159,  34:78.96,      35:79.904})
amu.update({ 36:83.80,     37:85.4678,   38:87.62,     39:88.90585,   40:91.224})
amu.update({ 41:92.90638,  42:95.94,     43:98.9062,   44:101.07,     45:102.9055})
amu.update({ 46:106.42,    47:107.8682,  48:112.411,   49:114.82,     50:118.710})
amu.update({ 51:121.753,   52:127.60,    53:126.90447, 54:131.29,     55:132.90543})
amu.update({ 56:137.327,   57:138.9055,  58:140.115,   59:140.90765,  60:144.24})
amu.update({ 61:147.91,    62:150.36,    63:151.965,   64:157.25,     65:158.92534})
amu.update({ 66:162.50,    67:164.93032, 68:167.26,    69:168.93421,  70:173.04})
amu.update({ 71:174.967,   72:178.49,    73:180.9479,  74:183.85,     75:186.207})
amu.update({ 76:190.2,     77:192.22,    78:195.08,    79:196.96654,  80:200.59})
amu.update({ 81:204.3833,  82:207.2,     83:208.98037, 84:209.0,      85:210.0})
amu.update({ 86:222.0,     87:223.0,     88:226.0254,  89:230.0,      90:232.0381})
amu.update({ 91:231.0359,  92:238.0289,  93:237.0482,  94:242.0,      95:243.0})
amu.update({ 96:247.0,     97:247.0,     98:249.0,     99:254.0,     100:253.0})
amu.update({101:256.0,    102:254.0,    103:257.0,    104:260.0})

