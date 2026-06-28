pipeline {
    agent any

    options {
        ansiColor('xterm')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        disableConcurrentBuilds()
        timestamps()
    }

    environment {
        APP_NAME = 'self-service-portal'
        AWS_REGION = 'ap-south-1'
        AWS_ACCOUNT_ID = credentials('aws-account-id')
        AWS_CREDENTIALS_ID = 'aws-jenkins-credentials'
        ECR_REGISTRY = "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
        ECR_REPOSITORY = 'self-service-portal'

        SONARQUBE_SERVER = 'sonarqube'
        GITOPS_REPO = 'git@github.com:your-org/ssp-gitops.git'
        GITOPS_CREDENTIALS_ID = 'gitops-ssh-key'
        GITOPS_BRANCH = 'main'
        GITOPS_APP_PATH = 'apps/self-service-portal'
        GITOPS_IMAGE_FILE = 'apps/self-service-portal/rollout.yaml'
        K8S_NAMESPACE = 'ssp'

        ARGOCD_APP = 'self-service-portal'
        SLACK_CHANNEL = '#deployments'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    env.IMAGE_TAG = "${env.BUILD_NUMBER}-${env.GIT_COMMIT.take(7)}"
                    env.IMAGE_URI = "${env.ECR_REGISTRY}/${env.ECR_REPOSITORY}:${env.IMAGE_TAG}"
                }
            }
        }

        stage('Validate, Scan and Build') {
            parallel {
                stage('Unit Test') {
                    steps {
                        sh '''
                            set -eux
                            VENV_DIR="$(mktemp -d)"
                            trap 'rm -rf "${VENV_DIR}"' EXIT
                            python3 -m venv "${VENV_DIR}"
                            . "${VENV_DIR}/bin/activate"
                            pip install --upgrade pip
                            pip install -r requirements.txt
                            if [ -f requirements-dev.txt ]; then
                              pip install -r requirements-dev.txt
                            fi
                            python -m compileall app.py migrations
                            if [ -d tests ]; then
                              pytest -q
                            else
                              echo "No tests directory found; compile checks completed."
                            fi
                        '''
                    }
                }

                stage('SonarQube') {
                    steps {
                        withSonarQubeEnv("${SONARQUBE_SERVER}") {
                            sh '''
                                set -eux
                                sonar-scanner \
                                  -Dsonar.projectKey=self-service-portal \
                                  -Dsonar.projectName=self-service-portal \
                                  -Dsonar.sources=. \
                                  -Dsonar.exclusions=.venv/**,instance/**,__pycache__/**,migrations/versions/**
                            '''
                        }
                    }
                }

                stage('Trivy Scan') {
                    steps {
                        sh '''
                            set -eux
                            trivy fs --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed .
                        '''
                    }
                }

                stage('Build Docker Image') {
                    steps {
                        sh '''
                            set -eux
                            docker build \
                              --label org.opencontainers.image.revision="${GIT_COMMIT}" \
                              --label org.opencontainers.image.source="${GIT_URL}" \
                              -t "${IMAGE_URI}" .
                        '''
                    }
                }
            }
        }

        stage('Quality Gate') {
            steps {
                timeout(time: 10, unit: 'MINUTES') {
                    waitForQualityGate abortPipeline: true
                }
            }
        }

        stage('Trivy Image Scan') {
            steps {
                sh '''
                    set -eux
                    trivy image --exit-code 1 --severity HIGH,CRITICAL --ignore-unfixed "${IMAGE_URI}"
                '''
            }
        }

        stage('Push to ECR') {
            steps {
                withCredentials([[$class: 'AmazonWebServicesCredentialsBinding', credentialsId: "${AWS_CREDENTIALS_ID}"]]) {
                    sh '''
                        set -eux
                        aws ecr describe-repositories --repository-names "${ECR_REPOSITORY}" --region "${AWS_REGION}" >/dev/null 2>&1 \
                          || aws ecr create-repository --repository-name "${ECR_REPOSITORY}" --region "${AWS_REGION}" >/dev/null
                        aws ecr get-login-password --region "${AWS_REGION}" \
                          | docker login --username AWS --password-stdin "${ECR_REGISTRY}"
                        docker push "${IMAGE_URI}"
                    '''
                }
            }
        }

        stage('Update GitOps Repository') {
            steps {
                sshagent(credentials: ["${GITOPS_CREDENTIALS_ID}"]) {
                    sh '''
                        set -eux
                        rm -rf gitops
                        git clone --branch "${GITOPS_BRANCH}" "${GITOPS_REPO}" gitops
                        cd gitops

                        if [ ! -f "${GITOPS_IMAGE_FILE}" ]; then
                          echo "GitOps image file not found: ${GITOPS_IMAGE_FILE}"
                          exit 1
                        fi

                        sed -i -E "s#image: .*${ECR_REPOSITORY}:.*#image: ${IMAGE_URI}#g" "${GITOPS_IMAGE_FILE}"
                        git config user.email "jenkins@local"
                        git config user.name "Jenkins CI"
                        git add "${GITOPS_APP_PATH}"

                        if git diff --cached --quiet; then
                          echo "GitOps repository already points to ${IMAGE_URI}"
                        else
                          git commit -m "Deploy ${APP_NAME} ${IMAGE_TAG}"
                          git push origin "${GITOPS_BRANCH}"
                        fi
                    '''
                }
            }
        }

        stage('ArgoCD Sync') {
            steps {
                sh '''
                    set -eux
                    if command -v argocd >/dev/null 2>&1; then
                      argocd app sync "${ARGOCD_APP}" --prune
                      argocd app wait "${ARGOCD_APP}" --health --sync --timeout 600
                    else
                      echo "argocd CLI not installed; ArgoCD will reconcile from GitOps automatically."
                    fi
                '''
            }
        }
    }

    post {
        success {
            slackSend(
                channel: "${SLACK_CHANNEL}",
                color: 'good',
                message: "SUCCESS: ${APP_NAME} ${IMAGE_TAG} pushed to ECR and promoted through GitOps. ${env.BUILD_URL}"
            )
        }
        failure {
            slackSend(
                channel: "${SLACK_CHANNEL}",
                color: 'danger',
                message: "FAILED: ${APP_NAME} build ${BUILD_NUMBER}. ${env.BUILD_URL}"
            )
        }
        always {
            cleanWs deleteDirs: true, notFailBuild: true
        }
    }
}
