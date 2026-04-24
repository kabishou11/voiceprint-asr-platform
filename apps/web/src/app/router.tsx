import { createBrowserRouter } from 'react-router-dom';

import { AppLayout } from '../components/AppLayout';
import { JobDetailPage } from '../pages/jobs/JobDetailPage';
import { JobListPage } from '../pages/jobs/JobListPage';
import { MeetingMinutesIndexPage } from '../pages/minutes/MeetingMinutesIndexPage';
import { MeetingMinutesPage } from '../pages/minutes/MeetingMinutesPage';
import { ModelManagementPage } from '../pages/system/ModelManagementPage';
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
        path: 'minutes',
        element: <MeetingMinutesIndexPage />,
      },
      {
        path: 'minutes/:jobId',
        element: <MeetingMinutesPage />,
      },
      {
        path: 'voiceprints',
        element: <VoiceprintLibraryPage />,
      },
      {
        path: 'system/models',
        element: <ModelManagementPage />,
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
