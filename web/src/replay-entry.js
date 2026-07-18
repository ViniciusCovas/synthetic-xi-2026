import './main.js';
import './replay.css';
import { mountReplayBroadcast } from './replay.js';

const main = document.querySelector('main');
if (main) {
  const methodSection = main.querySelector('.method-section');
  const replaySection = document.createElement('section');
  replaySection.id = 'replay-broadcast';
  replaySection.className = 'replay-section';
  if (methodSection) main.insertBefore(replaySection, methodSection);
  else main.appendChild(replaySection);
  await mountReplayBroadcast(replaySection);
}
