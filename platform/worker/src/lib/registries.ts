export abstract class WorkflowBase {
  abstract name: string;
  abstract run(input: unknown): Promise<unknown>;
}

export interface CronEntry {
  name: string;
  handler: () => void | Promise<void>;
  schedule: string;
}

const crons = new Map<string, CronEntry>();

export const cronRegistry = {
  registerCron(name: string, handler: () => void | Promise<void>, schedule: string): void {
    crons.set(name, { name, handler, schedule });
  },
  getCron(name: string): CronEntry | undefined {
    return crons.get(name);
  },
  listCrons(): CronEntry[] {
    return Array.from(crons.values());
  },
};

const workflows = new Map<string, WorkflowBase>();

export function registerWorkflow(name: string, workflow: WorkflowBase): void {
  workflows.set(name, workflow);
}

export function getWorkflow(name: string): WorkflowBase | undefined {
  return workflows.get(name);
}
