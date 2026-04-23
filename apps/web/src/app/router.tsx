import { createBrowserRouter } from 'react-router-dom';

import { AppLayout } from '../components/AppLayout';
import { JobDetailPage } from '../pages/jobs/JobDetailPage';
import { JobListPage } from '../pages/jobs/JobListPage';
import { ModelManagementPage } from '../pages/system/ModelManagementPage';
import { ModelRegistryPage } from '../pages/system/ModelRegistryPage';
import { TaskQueuePage } from '../pages/tasks/TaskQueuePage';
import { TranscriptionWorkbenchPage } from '../pages/transcription/TranscriptionWorkbenchPage';
import { VoiceprintLibraryPage } from '../pages/voiceprints/VoiceprintLibraryPage';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      {
        index: true,
        element: <TranscriptionWorkbenchPage />,
      },
      {
        path: 'jobs',
        element: <JobListPage />,
      },
      {
        path: 'jobs/:jobId',
        element: <JobDetailPage />,
      },
      {
        path: 'voiceprints',
        element: <VoiceprintLibraryPage />,
      },
      {
        path: 'system/models',
        element: <ModelRegistryPage />,
      },
      {
        path: 'system/management',
        element: <ModelManagementPage />,
      },
      {
        path: 'tasks',
        element: <TaskQueuePage />,
      },
    ],
  },
]);
