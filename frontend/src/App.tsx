import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { ToastProvider } from "@/components/ToastContext";
import { AITaskProvider } from "@/contexts/AITaskContext";
import { LoginPage } from "@/auth/LoginPage";
import { QuestionList } from "@/pages/questions/QuestionList";
import { QuestionCreate } from "@/pages/questions/QuestionCreate";
import { QuestionDetail } from "@/pages/questions/QuestionDetail";
import { AnswerDetail } from "@/pages/answers/AnswerDetail";
import { ReviewQueue } from "@/pages/reviews/ReviewQueue";
import { ReviewDetail } from "@/pages/reviews/ReviewDetail";
import { QuestionReviewQueue } from "@/pages/admin/QuestionReviewQueue";
import { ServiceAccounts } from "@/pages/admin/ServiceAccounts";
import { AILogs } from "@/pages/admin/AILogs";
import { AIControls } from "@/pages/admin/AIControls";
import { SourceDocuments } from "@/pages/admin/SourceDocuments";
import { MLExport } from "@/pages/admin/MLExport";
import { Settings } from "@/pages/settings/Settings";

function App() {
  return (
    <ToastProvider>
    <AITaskProvider>
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
        <Route path="/" element={<Navigate to="/questions" replace />} />
        <Route path="/questions" element={<QuestionList />} />
        <Route path="/questions/new" element={<QuestionCreate />} />
        <Route path="/questions/:id" element={<QuestionDetail />} />
        <Route path="/answers/:id" element={<AnswerDetail />} />

        <Route path="/reviews" element={<ProtectedRoute requiredRole="reviewer"><ReviewQueue /></ProtectedRoute>} />
        <Route path="/reviews/:id" element={<ReviewDetail />} />

        <Route path="/settings" element={<ProtectedRoute requiredRole="admin"><Settings /></ProtectedRoute>} />

        <Route path="/admin/questions" element={<ProtectedRoute requiredRole="admin"><QuestionReviewQueue /></ProtectedRoute>} />
        <Route path="/admin/service-accounts" element={<ProtectedRoute requiredRole="admin"><ServiceAccounts /></ProtectedRoute>} />
        <Route path="/admin/ai-logs" element={<ProtectedRoute requiredRole="admin"><AILogs /></ProtectedRoute>} />
        <Route path="/admin/ai" element={<ProtectedRoute requiredRole="admin"><AIControls /></ProtectedRoute>} />
        <Route path="/admin/source-documents" element={<ProtectedRoute requiredRole="admin"><SourceDocuments /></ProtectedRoute>} />
        <Route path="/admin/ml-export" element={<ProtectedRoute requiredRole="admin"><MLExport /></ProtectedRoute>} />
      </Route>
    </Routes>
    </AITaskProvider>
    </ToastProvider>
  );
}

export default App;
