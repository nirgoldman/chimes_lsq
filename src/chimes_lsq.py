import sys
import numpy
import scipy.linalg
import math as m
import subprocess
import os
import argparse

from numpy        import *
from numpy.linalg import lstsq
from datetime     import *
from subprocess   import call


#############################################
#############################################
# Main
#############################################
#############################################

def main():
    
    loc = os.getcwd()
    
    
    #############################################
    # Define arguments supported by the lsq code
    #############################################
        
    parser = argparse.ArgumentParser(description='Least-squares force matching based on output of chimes_lsq')

    parser.add_argument("--A",                    type=str,      default='A.txt',         help='A (derivative) matrix') 
    parser.add_argument("--algorithm",            type=str,      default='svd',           help='fitting algorithm')
    parser.add_argument("--dlasso_dlars_path",    type=str     , default='',              help='Path to DLARS and/or DLASSO solver')
    parser.add_argument("--alpha",                type=float,    default=1.0e-04,         help='Lasso regularization')
    parser.add_argument("--b",                    type=str,      default='b.txt',         help='b (force) file')
    parser.add_argument("--cores",                type=int,      default=8,               help='DLARS number of cores')
    parser.add_argument("--eps",                  type=float,    default=1.0e-05,         help='svd regularization')
    parser.add_argument("--header",               type=str,      default='params.header', help='parameter file header')
    parser.add_argument("--map",                  type=str,      default='ff_groups.map', help='parameter file map')
    parser.add_argument("--nodes",                type=int,      default=1,               help='DLARS number of nodes')
    parser.add_argument("--normalize",            type=str2bool, default=False,           help='Normalize DLARS calculation')
    parser.add_argument("--read_output",          type=str2bool, default=False,           help='Read output from previous DLARS run')
    parser.add_argument("--restart_dlasso_dlars", type=str,      default="",              help='Determines whether dlasso or dlars job will be restarted. Argument is the restart file name ')
    parser.add_argument("--split_files",          type=str2bool, default=False,           help='LSQ code has split A matrix output.  Works DLARS.')
    parser.add_argument("--test_suite",           type=str2bool, default=False,           help='output for test suite')
    parser.add_argument("--weights",              type=str,      default="None",          help='weight file')
    parser.add_argument("--active",               type=str2bool, default=False,           help='is this a DLARS/DLASSO run from the active learning driver?')

    # Actually parse the arguments

    args        = parser.parse_args()
    
    dlasso_dlars_path = loc + '../../contrib/dlars/src/'
    
    if args.dlasso_dlars_path != '':
        dlasso_dlars_path = args.dlasso_dlars_path

    #############################################
    # Import sklearn modules, if needed
    #############################################

    # Algorithms requiring sklearn.
    sk_algos = ["lasso", "lassolars", "lars"] ;
        
    if args.algorithm in sk_algos:
        from sklearn import linear_model
        from sklearn import preprocessing
        
    #############################################
    # Read weights, if used
    #############################################        
        
        
    if ( args.weights == "None" ):
        DO_WEIGHTING = False 
    else:
        DO_WEIGHTING = True
        if ( not args.split_files ):
            WEIGHTS= numpy.genfromtxt(args.weights,dtype='float')

    #################################
    #   Process A and b matrices, sanity check weight dimensions
    #################################

    # Use genfromtxt to avoid parsing large files. Note that the AL driver does not use split matrices
    
    if (args.active  and not args.split_files) or ((args.algorithm == "dlasso") and not args.split_files): 
    
        A      = numpy.zeros((1,1),dtype=float)
        b      = numpy.genfromtxt(args.b, dtype='float') 
        np     = "undefined"
        nlines = b.shape[0]

    elif ( (not args.split_files) and (not args.read_output) ) :
        A       = numpy.genfromtxt(args.A , dtype='float')
        nlines  = A.shape[0] 
        np      = A.shape[1] 
        b       = numpy.genfromtxt(args.b, dtype='float') 
        nlines2 = b.shape[0] 

        if ( nlines != nlines2 ):
            print "Error: the number of lines in the input files do not match\n"
            exit(1) 

            if np > nlines:
                print "Error: number of variables > number of equations"
                exit(1)
    else:
        
        if not args.read_output:
            dimf = open("dim.0000.txt", "r") ;
            line = next(dimf) 
            dim  = (int(x) for x in line.split())
            A    = numpy.zeros((1,1),dtype=float)           # Dummy A matrix - NOT read in.
            b    = numpy.genfromtxt(args.b, dtype='float')  # Dummy b matrix - NOT read in.
            (np, nstart, nend, nlines) = dim
        else:
            b      = numpy.genfromtxt(args.b, dtype='float') 
            np     = "undefined"
            nlines = b.shape[0]
            
    # Sanity check weight dimensions        
    
    if DO_WEIGHTING and not args.split_files:
        if ( WEIGHTS.shape[0] != nlines ):
            print "Wrong number of lines in WEIGHTS file"
            exit(1)  

    #################################
    # Apply weighting to A and b
    #################################

    weightedA = None
    weightedb = None

    if DO_WEIGHTING and not args.split_files and not args.active  and not (args.algorithm == "dlasso"):

        # This way requires too much memory for long A-mat's
        # to avoid a memory error, we will do it the slow way:

        weightedA = numpy.zeros((A.shape[0],A.shape[1]),dtype=float)
        weightedb = numpy.zeros((A.shape[0],),dtype=float)

        for i in xrange(A.shape[0]):     # Loop over rows (atom force components)
            for j in xrange(A.shape[1]): # Loop over cols (variables in fit)
                weightedA[i][j] = A[i][j]*WEIGHTS[i]
                weightedb[i]    = b[i]   *WEIGHTS[i]

    #################################
    # Solve the matrix equation
    #################################

    if args.algorithm == 'svd':
        
        # Make the scipy call
        
        print '! svd algorithm used'
        try:
            if DO_WEIGHTING: # Then it's OK to overwrite weightedA.  It is not used to calculate y (predicted forces) below.
                U,D,VT = scipy.linalg.svd(weightedA,overwrite_a=True)
                Dmat   = array((transpose(weightedA)))
            else:            #  Then do not overwrite A.  It is used to calculate y (predicted forces) below.
                U,D,VT = scipy.linalg.svd(A,overwrite_a=False)
                Dmat   = array((transpose(A)))  
        except LinAlgError:
            sys.stderr.write("SVD algorithm failed")
            exit(1)
            
        # Process output

        dmax = 0.0

        for i in range(0,len(Dmat)):
            if ( abs(D[i]) > dmax ) :
                dmax = abs(D[i])

            for j in range(0,len(Dmat[i])):
                Dmat[i][j]=0.0

        # Cut off singular values based on fraction of maximum value as per numerical recipes.
        
        eps=args.eps * dmax
        nvars = 0

        for i in xrange(0,len(D)):
            if abs(D[i]) > eps:
                Dmat[i][i]=1.0/D[i]
                nvars += 1

        print "! eps (= args.eps*dmax) =  ", eps        
        print "! SVD regularization factor = ", args.eps

        x=dot(transpose(VT),Dmat)

        if DO_WEIGHTING:
            x = dot(x,dot(transpose(U),weightedb))
        else:
            x = dot(x,dot(transpose(U),b))

    elif args.algorithm == 'lasso':
        
        # Make the sklearn call
        
        print '! Lasso regression used'
        print '! Lasso alpha = ' + str(args.alpha)
        reg   = linear_model.Lasso(alpha=args.alpha,fit_intercept=False,max_iter=100000)
        reg.fit(A,b)
        x     = reg.coef_
        np    = count_nonzero_vars(x)
        nvars = np

    elif args.algorithm == 'lassolars':
        
        # Make the sklearn call
        
        print '! LARS implementation of LASSO used'
        print '! LASSO alpha = ', args.alpha

        if DO_WEIGHTING:
            reg = linear_model.LassoLars(alpha=args.alpha,fit_intercept=False,fit_path=False,verbose=True,max_iter=100000, copy_X=False)
            reg.fit(weightedA,weightedb)
        else:
            reg = linear_model.LassoLars(alpha=args.alpha,fit_intercept=False,fit_path=False,verbose=True,max_iter=100000)
            reg.fit(A,b)
        x       = reg.coef_[0]
        np      = count_nonzero_vars(x)
        nvars   = np

    elif args.algorithm == 'dlars' or args.algorithm == 'dlasso' :
        
        # Make the DLARS or DLASSO call

        x,y = fit_dlars(dlasso_dlars_path, args.nodes, args.cores, args.alpha, args.split_files, args.algorithm, args.read_output, args.weights, args.normalize, args.A , args.b ,args.restart_dlasso_dlars)
        np = count_nonzero_vars(x)
        nvars = np
        
    else:

        print "Unrecognized fitting algorithm" 
        exit(1)

    #################################
    # Process output from solver(s)
    #################################

    # If split_files, A is not read in ...This conditional should really be set by the algorithm, since many set  y themselves...  
      
    if ( (not args.split_files) and (not args.read_output) and (not args.active ) and (args.algorithm != "dlasso") ):
        y=dot(A,x)
        
    Z=0.0

    # Put calculated forces in force.txt
    
    yfile = open("force.txt", "w")
    
    for a in range(0,len(b)):
        Z = Z + (y[a] - b[a]) ** 2.0
        yfile.write("%13.6e\n"% y[a]) 

    bic = float(nlines) * log(Z/float(nlines)) + float(nvars) * log(float(nlines))

    #############################################
    # Setup output
    #############################################
    
    print "! Date ", date.today() 
    print "!"
    print "! Number of variables            = ", np
    print "! Number of equations            = ", nlines
    print "! RMS force error                = " , sqrt(Z/float(nlines))
    print "! max abs variable               = ",  max(abs(x))
    print "! number of fitting vars         = ", nvars
    print "! Bayesian Information Criterion = ", bic
    if args.weights !="None":
        print '! Using weighting file:            ',args.weights
    print "!"

    ####################################
    # Actually process the header file...
    ####################################

    hf = open(args.header ,"r").readlines()

    BREAK_COND = False

    # Figure out whether we have triplets and/or quadruplets
    # Find the ATOM_TRIPS_LINE and ATOM_QUADS_LINE
    # Find the TOTAL_TRIPS and TOTAL_QUADS

    ATOM_TRIPS_LINE = 0
    ATOM_QUADS_LINE = 0
    TOTAL_TRIPS = 0
    TOTAL_QUADS = 0

    for i in range(0, len(hf)):
        print hf[i].rstrip('\n')
        TEMP = hf[i].split()
        if len(TEMP)>3:
            if (TEMP[2] == "TRIPLETS:"):
                TOTAL_TRIPS = TEMP[3]
                ATOM_TRIPS_LINE = i

                for j in range(i, len(hf)):
                    TEMP = hf[j].split()
                    if len(TEMP)>3:
                        if (TEMP[2] == "QUADRUPLETS:"):
                            print hf[j].rstrip('\n')
                            TOTAL_QUADS = TEMP[3]
                            ATOM_QUADS_LINE = j
                            BREAK_COND = True
                            break
            if (BREAK_COND):
                 break

    # 1. Figure out what potential type we have

    POTENTIAL = hf[5].split()
    POTENTIAL = POTENTIAL[1]

    print ""

    print "PAIR " + POTENTIAL + " PARAMS \n"

    # 2. Figure out how many coeffs each atom type will have

    SNUM_2B = 0
    SNUM_4B = 0

    if POTENTIAL == "CHEBYSHEV":
        
        TMP = hf[5].split()

        if len(TMP) >= 4:
            if len(TMP) >= 5:
                SNUM_4B = int(TMP[4])

            SNUM_2B = int(TMP[2])  
 

    # 3. Print out the parameters

    FIT_COUL = hf[1].split()
    FIT_COUL = FIT_COUL[1]

    ATOM_TYPES_LINE  = 7
    TOTAL_ATOM_TYPES = hf[ATOM_TYPES_LINE].split()
    TOTAL_ATOM_TYPES = int(TOTAL_ATOM_TYPES[2])
    ATOM_PAIRS_LINE  = ATOM_TYPES_LINE+2+TOTAL_ATOM_TYPES+2
    TOTAL_PAIRS      = hf[ATOM_PAIRS_LINE].split()
    TOTAL_PAIRS      = int(TOTAL_PAIRS[2])

    A1 = ""
    A2 = ""

    P1 = ""
    P2 = ""
    P3 = ""

    # PAIRS, AND CHARGES

    # Figure out how many 3B parameters there are

    SNUM_3B   = 0
    ADD_LINES = 0
    COUNTED_COUL_PARAMS = 0 

    if TOTAL_TRIPS > 0:
        for t in xrange(0, int(TOTAL_TRIPS)):

            P1 = hf[ATOM_TRIPS_LINE+3+ADD_LINES].split()

            if P1[4] != "EXCLUDED:":
                SNUM_3B +=  int(P1[4])

                TOTL = P1[6]
                ADD_LINES += 5

                for i in xrange(0, int(TOTL)):
                    ADD_LINES += 1

    # Figure out how many 4B parameters there are

    SNUM_4B   = 0
    ADD_LINES = 0

    if TOTAL_QUADS > 0:
        for t in xrange(0, int(TOTAL_QUADS)):

            P1 = hf[ATOM_QUADS_LINE+3+ADD_LINES].split()

            #print "QUAD HEADER", P1
            if P1[7] != "EXCLUDED:":

                SNUM_4B +=  int(P1[7])

                TOTL = P1[9]

                ADD_LINES += 5

                for i in xrange(0,int(TOTL)):
                    ADD_LINES += 1

    for i in range(0,TOTAL_PAIRS):

        A1 = hf[ATOM_PAIRS_LINE+2+i+1].split()
        A2 = A1[2]
        A1 = A1[1]

        print "PAIRTYPE PARAMS: " + `i` + " " + A1 + " " + A2 + "\n"

        for j in range(0, int(SNUM_2B)):
            print `j` + " " + `x[i*SNUM_2B+j]`

        if FIT_COUL == "true":
            print "q_" + A1 + " x q_" + A2 + " " + `x[TOTAL_PAIRS*SNUM_2B + SNUM_3B + SNUM_4B + i]`
            COUNTED_COUL_PARAMS += 1

        print " "

    # TRIPLETS

    ADD_LINES = 0
    ADD_PARAM = 0

    COUNTED_TRIP_PARAMS = 0

    if TOTAL_TRIPS > 0:
        print "TRIPLET " + POTENTIAL + " PARAMS \n"

        TRIP_PAR_IDX = 0

        for t in xrange(0, int(TOTAL_TRIPS)):

            PREV_TRIPIDX = 0

            print "TRIPLETTYPE PARAMS:"
            print "  " + hf[ATOM_TRIPS_LINE+2+ADD_LINES].rstrip() 

            P1 = hf[ATOM_TRIPS_LINE+3+ADD_LINES].split()

            #print "HEADER: ", P1

            V0 = P1[1] 
            V1 = P1[2]
            V2 = P1[3]

            if P1[4] == "EXCLUDED:" :
                print "   PAIRS: " + V0 + " " + V1 + " " + V2 + " EXCLUDED:"
                ADD_LINES += 1
            else:
                UNIQ = P1[4]
                TOTL = P1[6].rstrip() 

                print "   PAIRS: " + V0 + " " + V1 + " " + V2 + " UNIQUE: " + UNIQ + " TOTAL: " + TOTL 
                print "     index  |  powers  |  equiv index  |  param index  |       parameter       "
                print "   ----------------------------------------------------------------------------"

                ADD_LINES += 3

                if(t>0):
                    ADD_PARAM += 1

                for i in xrange(0,int(TOTL)):
                    ADD_LINES += 1
                    LINE       = hf[ATOM_TRIPS_LINE+2+ADD_LINES].rstrip('\n')
                    LINE_SPLIT = LINE.split()

                    print LINE + " " + `x[TOTAL_PAIRS*SNUM_2B + TRIP_PAR_IDX+int(LINE_SPLIT[5])]`

                TRIP_PAR_IDX += int(UNIQ)
                COUNTED_TRIP_PARAMS += int(UNIQ)
                #print "COUNTED_TRIP_PARAMS", COUNTED_TRIP_PARAMS

            print ""

            ADD_LINES += 2

    ADD_LINES = 0
    
    # QUADS    

    COUNTED_QUAD_PARAMS = 0
    if TOTAL_QUADS > 0:
        print "QUADRUPLET " + POTENTIAL + " PARAMS \n"

        QUAD_PAR_IDX = 0

        for t in xrange(int(TOTAL_QUADS)):

            PREV_QUADIDX = 0

            #print "ATOM_QUADS_LINE " + str(ATOM_QUADS_LINE+2+ADD_LINES)

            P1 = hf[ATOM_QUADS_LINE+2+ADD_LINES].split()

            #print "P1 " + P1[1] + P1[2] + P1[3] + P1[4] + P1[5] + P1[6]

            print "QUADRUPLETYPE PARAMS: " 
            print "  " + hf[ATOM_QUADS_LINE+2+ADD_LINES].rstrip() 

            P1 = hf[ATOM_QUADS_LINE+3+ADD_LINES].split()

            #print P1 

            V0 = P1[1] 
            V1 = P1[2]
            V2 = P1[3]
            V3 = P1[4] 
            V4 = P1[5]
            V5 = P1[6]

            #print "UNIQUE: ", str(UNIQ)
            if P1[7] == "EXCLUDED:" :
                print "   PAIRS: " + V0 + " " + V1 + " " + V2 + " " + V3 + " " + V4 + " " + V5 + " EXCLUDED: " 
                ADD_LINES += 1

            else:
                UNIQ = P1[7]
                TOTL = P1[9].rstrip() 

                print "   PAIRS: " + V0 + " " + V1 + " " + V2 + " " + V3 + " " + V4 + " " + V5 + " UNIQUE: " + UNIQ + " TOTAL: " + TOTL 
                print "     index  |  powers  |  equiv index  |  param index  |       parameter       "
                print "   ----------------------------------------------------------------------------"

                ADD_LINES += 3

                if(t>0):
                    ADD_PARAM += 1

                for i in xrange(0,int(TOTL)):
                    ADD_LINES += 1
                    LINE       = hf[ATOM_QUADS_LINE+2+ADD_LINES].rstrip('\n')
                    LINE_SPLIT = LINE.split()

                    UNIQ_QUAD_IDX = int(LINE_SPLIT[8])
                    #print 'UNIQ_QUAD_IDX', str(UNIQ_QUAD_IDX)

                    print LINE + " " + `x[TOTAL_PAIRS*SNUM_2B + COUNTED_TRIP_PARAMS + QUAD_PAR_IDX + UNIQ_QUAD_IDX]`

                QUAD_PAR_IDX += int(UNIQ)
                COUNTED_QUAD_PARAMS += int(UNIQ)

            print ""

            ADD_LINES += 2

    # Remaining tidbids

    mapsfile=open(args.map,"r").readlines()

    print ""

    for i in range(0,len(mapsfile)):
        print mapsfile[i].rstrip('\n')

    print ""

    total_params = TOTAL_PAIRS * SNUM_2B + COUNTED_TRIP_PARAMS + COUNTED_QUAD_PARAMS + COUNTED_COUL_PARAMS 

    N_ENER_OFFSETS = int(hf[7].split()[2])

## Parameter count could be off by natom_types, if energies are included in the fit
    if (total_params != len(x)) and (len(x) != (total_params+N_ENER_OFFSETS)) :
        sys.stderr.write( "Error in counting parameters\n") 
        sys.stderr.write("len(x) " + str(len(x)) + "\n") 
        sys.stderr.write("TOTAL_PAIRS " + str(TOTAL_PAIRS) + "\n") 
        sys.stderr.write("SNUM_2B " + str(SNUM_2B) + "\n") 
        sys.stderr.write("COUNTED_TRIP_PARAMS " + str(COUNTED_TRIP_PARAMS) + "\n") 
        sys.stderr.write("COUNTED_QUAD_PARAMS " + str(COUNTED_QUAD_PARAMS) + "\n")
        sys.stderr.write("COUNTED_COUL_PARAMS " + str(COUNTED_COUL_PARAMS) + "\n")
        exit(1)


    if len(x) == (total_params+N_ENER_OFFSETS):
        print "NO ENERGY OFFSETS: ", N_ENER_OFFSETS
    
        for i in xrange(N_ENER_OFFSETS):
            print "ENERGY OFFSET " + `i+1` + " " + str(x[total_params+i])

    print "ENDFILE"		
    return 0

#############################################
#############################################
# Small helper functions
#############################################
#############################################

def is_number(s):
# Test if s is a number.
    try:
        float(s)
        return True
    except ValueError:
        return False


def str2bool(v):
## Convert string to bool.  Used in command argument parsing.
    if v.lower() in ('yes', 'true', 't', 'y'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n'):
        return False
    else:
        raise argparse.ArgumentTypeError("Boolean value expected")
                       

def count_nonzero_vars(x):
    np = 0
    for i in xrange(0, len(x)):
        if ( abs(x[i]) > 1.0e-05 ):
            np = np + 1
    return np


#############################################
#############################################
# DLARS wrapper
#############################################
#############################################

def fit_dlars(dlasso_dlars_path, nodes, cores, alpha, split_files, algorithm, read_output, weights, normalize, A , b, restart_dlasso_dlars):

    # Use the Distributed LARS/LASSO fitting algorithm.  Returns both the solution x and
    # the estimated force vector A * x, which is read from Ax.txt.    
    
    if dlasso_dlars_path == '':
        print "ERROR: DLARS/DLASSO  path not provided."
        print "Please run again with --dlasso_dlars_path </absolute/path/to/dlars/dlasso/src/>"
        exit(0)

    if args.algorithm == 'dlasso' :
        print '! DLARS code for LASSO used'
    elif args.algorithm == 'dlars' :
        print '! DLARS code for LARS used'
    else:
        print "Bad algorithm in fit_dlars:" + args.algorithm
        exit(1)
    print '! DLARS alpha = ' + str(args.alpha)

    if not args.read_output:
    
        exepath = "srun -N " + str(args.nodes) + " -n " + str(args.cores) + " "
        
        exepath = exepath + dlasso_dlars_path + "dlars"
        
        if os.path.exists(dlars_file):

            command = None
   
            command = exepath + " " + args.A  + " " + args.b + " dim.txt --lambda=" + `args.alpha`

            #else:
            #    command = ("{0} A.txt b.txt dim.txt --lambda={1}".format(exepath, args.alpha))

            if ( args.split_files ) :
                command = command + " --split_files"
            if ( args.algorithm == 'dlars' ):
                command = command + " --algorithm=lars"
            elif ( args.algorithm == 'dlasso' ):
                command = command + " --algorithm=lasso"

            if ( args.weights != 'None' ):
                command = command + " --weights=" + args.weights

            if ( args.normalize ):
                command = command + " --normalize=y" 
            else:
                command = command + " --normalize=n" 

            if args.restart_dlasso_dlars != "":
                print "Will run a dlars/dlasso restart job with file:", args.restart_dlasso_dlars

                command = command + " --restart=" + args.restart_dlasso_dlars
                
                command = command +  " >& dlars.log"

            print("! DLARS run: " + command + "\n")

            if ( os.system(command) != 0 ) :
                print(command + " failed")
                sys.exit(1)
        else:
            print exepath + " does not exist"
            sys.exit(1)
    else:
        print "! Reading output from prior DLARS calculation"

    x = numpy.genfromtxt("x.txt", dtype='float')
    y = numpy.genfromtxt("Ax.txt", dtype='float') 
    return x,y



# Python magic to allow having a main function definition.    
if __name__ == "__main__":
    main()
    














