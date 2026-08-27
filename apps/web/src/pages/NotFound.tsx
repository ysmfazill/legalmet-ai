import { Link } from 'react-router-dom';

import { PageHeader } from '../components/PageHeader';
import { EmptyState } from '../components/states';

export function NotFoundPage() {
  return (
    <div className="page">
      <PageHeader eyebrow="404" title="Page not found" />
      <div className="card">
        <div className="card__body">
          <EmptyState
            icon="search"
            title="This page could not be found"
            message="The page you are looking for may have moved, or the link is incorrect."
            action={
              <Link className="btn btn--primary" to="/">
                Back to Command Center
              </Link>
            }
          />
        </div>
      </div>
    </div>
  );
}
