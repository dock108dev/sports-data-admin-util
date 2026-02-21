import { request } from "./client";

export interface TriggerTaskResponse {
  status: string;
  task_name: string;
  task_id: string;
}

export async function triggerTask(
  taskName: string,
  args: unknown[]
): Promise<TriggerTaskResponse> {
  return request("/api/admin/tasks/trigger", {
    method: "POST",
    body: JSON.stringify({ task_name: taskName, args }),
  });
}
