import { ComponentFixture, TestBed } from '@angular/core/testing';

import { ProjectMetricsPanelComponent } from './project-metrics-panel.component';

describe('ProjectMetricsPanelComponent', () => {
  let component: ProjectMetricsPanelComponent;
  let fixture: ComponentFixture<ProjectMetricsPanelComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProjectMetricsPanelComponent]
    })
    .compileComponents();

    fixture = TestBed.createComponent(ProjectMetricsPanelComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
