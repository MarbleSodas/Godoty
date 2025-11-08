import { Routes } from '@angular/router';
import { DebugDashboardComponent } from './components/debug-dashboard/debug-dashboard.component';
import { AgentConfigComponent } from './components/agent-config/agent-config.component';

export const routes: Routes = [
  { path: 'debug', component: DebugDashboardComponent },
  { path: 'agent-config', component: AgentConfigComponent },
];

