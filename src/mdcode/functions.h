#ifndef _HELPERS_
#define _HELPERS_


#include<stdio.h>
#include<iostream>
#include<math.h>
#include<stdlib.h>
#include "functions.h"
using namespace std;

static double ke=332.0637157615209;//converter between electron units and Stillinger units for Charge*Charge.

static double Hartree = 627.50961 ; // 1 Hartree in kcal/mol.
static double Kb  = 0.001987 ; // Boltzmann constant in kcal/mol-K.
static double Tfs = 48.888 ;   // Internal time unit in fs.

void ZCalc(double **Coord, string *Lb, double *Q, double *Latcons,const int nlayers,
	   const int nat,const double smin,const double smax,
	   const double sdelta,const int snum, 
	   double *params, double *pot_params, bool if_cheby,
	   double **SForce,double& Vtot,double& Pxyz) ;

void ZCalc_Ewald(double **Coord, string *Lb, double *Q, double *Latcons,const int nlayers,
		 const int nat,const double smin,const double smax,
		 const double sdelta,const int snum, 
		 double *params,double **SForce,double& Vtot,double& Pxyz) ;
void ZCalc_Ewald_Orig(double **Coord,string *Lb, double *Latcons,
		      const int nat,double **SForce,double& Vtot,double& Pxyz) ;

double bondedpot(double **Coord_bonded,double ***I_bonded);
double spline_pot(double smin, double smax, double sdelta, double rlen2, double *params, double *pot_params, int snum, int vstart, double &S_r) ;


#endif

