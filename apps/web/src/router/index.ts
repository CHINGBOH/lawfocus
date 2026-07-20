import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      name: 'laws',
      component: () => import('../views/LawListView.vue'),
    },
    {
      path: '/laws/:lawCode/versions/:versionName/articles/:articleNo?',
      name: 'article-reader',
      component: () => import('../views/ArticleReaderView.vue'),
      props: true,
    },
    {
      path: '/subjects',
      name: 'subjects',
      component: () => import('../views/SubjectListView.vue'),
    },
    {
      path: '/subjects/:subjectId/governance',
      name: 'subject-governance',
      component: () => import('../views/SubjectGovernanceView.vue'),
      props: true,
    },
    {
      path: '/subjects/:subjectId/facts',
      name: 'subject-facts',
      component: () => import('../views/FactEvidenceView.vue'),
      props: true,
    },
    {
      path: '/compliance-checks/new',
      name: 'compliance-check-new',
      component: () => import('../views/ComplianceCheckWizardView.vue'),
    },
    {
      path: '/compliance-checks/:checkId',
      name: 'compliance-check-result',
      component: () => import('../views/ComplianceCheckResultView.vue'),
      props: true,
    },
    {
      path: '/conclusions/:conclusionId/proof',
      name: 'conclusion-proof',
      component: () => import('../views/ConclusionProofView.vue'),
      props: true,
    },
    {
      path: '/rules',
      name: 'rules',
      component: () => import('../views/RuleListView.vue'),
    },
    {
      path: '/rules/:ruleId',
      name: 'rule-detail',
      component: () => import('../views/RuleDetailView.vue'),
      props: true,
    },
    {
      path: '/facts/:factId',
      name: 'fact-detail',
      component: () => import('../views/FactDetailView.vue'),
      props: true,
    },
    {
      path: '/workbench',
      name: 'workbench',
      component: () => import('../views/WorkbenchView.vue'),
    },
    {
      path: '/audit',
      name: 'audit',
      component: () => import('../views/AuditView.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (auth.isAuthenticated && auth.me === null) {
    try {
      await auth.fetchMe()
    } catch {
      // Stale/expired token — treat as logged out rather than surfacing an
      // unhandled rejection or leaving the session in a half-authenticated state.
      auth.logout()
      if (!to.meta.public) {
        return { name: 'login', query: { redirect: to.fullPath } }
      }
    }
  }
  return true
})

export default router
