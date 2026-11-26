#ifndef RBM_U340E_HYDRAULIC_WORKSPACE_H
#define RBM_U340E_HYDRAULIC_WORKSPACE_H

#include "factory_hydraulics.h"

/* Equivalent to factory_hydraulics_control_main. The caller owns an
 * exclusive workspace disjoint from state. State is committed only on
 * success. Workspace contents are transient during and after the call. */
int rbm_u340e_hydraulics_control_main_workspace(FactoryHydraulics *state, FactoryHydraulics *workspace);

#endif
