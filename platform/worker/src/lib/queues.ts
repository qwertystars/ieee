import type { Env } from '../index';
import { ulid } from './ulid';

interface EnqueueInput {
  body: Record<string, unknown>;
  delaySeconds?: number;
}

function makeEnqueue(envKey: keyof Env) {
  return async (env: Env, input: EnqueueInput) => {
    const queue = env[envKey] as Queue<Record<string, unknown>>;
    const idempotencyKey = ulid();
    const message: Record<string, unknown> = {
      ...input.body,
      __idempotencyKey: idempotencyKey,
    };
    const options: QueueSendOptions = {};
    if (input.delaySeconds !== undefined) {
      options.delaySeconds = input.delaySeconds;
    }
    await queue.send(message, options);
    return idempotencyKey;
  };
}

export const enqueueIngest = makeEnqueue('ingestQ');
export const enqueueAlert = makeEnqueue('alertQ');
export const enqueueAi = makeEnqueue('aiQ');
export const enqueueDrone = makeEnqueue('droneQ');
export const enqueueGeocode = makeEnqueue('geocodeQ');
export const enqueueWebhookIngest = makeEnqueue('webhookIngestQ');
export const enqueueWebhookDelivery = makeEnqueue('webhookDeliveryQ');
